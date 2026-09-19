from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, UploadFile, status

from labpilot.api import services
from labpilot.api.contracts import Ingested
from labpilot.api.errors import (
    SourceTooLargeToIngest,
    StorageUnavailable,
    UnreadableSource,
    UnsafeArchiveUpload,
)
from labpilot.api.schemas import ErrorEnvelope, IngestResponse
from labpilot.api.uploads import read_artifact
from labpilot.ingest import Side
from labpilot.sources import (
    CloneFailed,
    SourceNotFound,
    SourceTooLarge,
    UnsafeArchive,
    UnsupportedURL,
    open_git,
    open_zip,
)
from labpilot.store import ConnectionFailed, NotConfigured, connect

router = APIRouter(tags=["artifacts"])

FAILURES = {
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "model": ErrorEnvelope,
        "description": "The upload, or the whole body, is over its limit.",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorEnvelope,
        "description": "The upload is unreadable, unnamed, empty, or a secret",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorEnvelope,
        "description": "the database or every embedder is unreachable",
    },
}


@router.post(
    "/artifacts",
    responses=FAILURES,
    status_code=status.HTTP_201_CREATED,
    summary="store artifact so later questions do not re-read it",
)
def ingest(
    side: Annotated[Side, Form()],
    file: UploadFile | None = None,
    url: Annotated[str | None, Form()] = None,
) -> IngestResponse:
    """Chunk, embed and store ONE artifact: a file, a .zip, or a git URL.

    This door exists so artifacts can be STATE rather than input. Under the old
    single endpoint every question re-chunked and re-embedded both sides -
    measured at about fifteen minutes per question for a FastAPI-sized
    repository. Here it is paid once.

    All three inputs collapse to the same shape after one step:

        a single file  ->  bytes   ->  chunk   ->  embed  ->  pgvector
        a .zip         ->  a folder on disk ->  walk  ->  ...
        a git URL      ->  a shallow clone  ->  walk  ->  ...

    Only "get me the files" differs; everything downstream is shared, which is
    why `_store` exists rather than three copies of the write path.

    It reports `slow` and does not wait: asking a human is the UI's job, and an
    HTTP handler that blocks on a person is one that times out.
    """
    if (file is None) == (url is None):
        raise UnreadableSource("send exactly one of `file` or `url`")

    try:
        with connect() as conn:
            result = _ingest(conn, side, file, url)
    except (NotConfigured, ConnectionFailed) as exc:
        raise StorageUnavailable(str(exc)) from exc
    except SourceTooLarge as exc:
        raise SourceTooLargeToIngest(str(exc)) from exc
    except UnsafeArchive as exc:
        raise UnsafeArchiveUpload(str(exc)) from exc
    except (CloneFailed, SourceNotFound, UnsupportedURL) as exc:
        raise UnreadableSource(str(exc)) from exc

    return IngestResponse(
        artifact_id=result.artifact.id,
        name=result.artifact.name,
        side=result.artifact.side,
        chunks=result.chunks,
        embedding_model=result.artifact.embedding_model,
        ingest_minutes=result.ingest_minutes,
        slow=result.ingest_minutes > services.WARN_MINUTES,
    )


def _ingest(conn, side: Side, file: UploadFile | None, url: str | None) -> Ingested:
    """One of three openers, then the same store path.

    The connection is opened by the CALLER, not here, because every function in
    store/ takes one - so the route is the layer that owns reaching the
    database and mapping the two ways that fails.
    """
    if url is not None:
        with open_git(url) as source:
            return services.ingest_source(conn, source, side=side)

    artifact = read_artifact(file, field="file")
    if not artifact.name.lower().endswith(".zip"):
        return services.ingest_artifact(
            conn, artifact.raw, name=artifact.name, side=side, field="file"
        )

    # open_zip takes a PATH, because a zip is read entry by entry rather than
    # held whole - which is also what lets it refuse a bomb from the header
    # before decompressing a single byte.
    with tempfile.TemporaryDirectory(prefix="labpilot-") as temporary:
        archive = Path(temporary) / artifact.name
        archive.write_bytes(artifact.raw)
        with open_zip(archive) as source:
            return services.ingest_source(conn, source, side=side)
