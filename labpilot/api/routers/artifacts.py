from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, UploadFile, status

from labpilot.api import services
from labpilot.api.errors import StorageUnavailable
from labpilot.api.schemas import ErrorEnvelope, IngestResponse
from labpilot.api.uploads import read_artifact
from labpilot.ingest import Side
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
    file: UploadFile,
) -> IngestResponse:
    """Chunk, embed and store one file.

    This door exists so artifacts can be STATE rather than input. Under the
    old single endpoint every question re-chunked and re-embedded both files -
    measured, 166 minutes per question for a FastAPI-sized repository. Here it
    is paid once.

    It reports `slow` and does not wait: asking a human is the UI's job, and
    an HTTP handler that blocks on a person is a handler that times out.
    """

    artifact = read_artifact(file, field="file")

    # The connection is opened HERE, not inside ingest_artifact, because
    # store/'s own functions all take one - so this is the layer that has to
    # own reaching the database, and mapping the two ways that fails.
    try:
        with connect() as conn:
            result = services.ingest_artifact(
                conn, artifact.raw, name=artifact.name, side=side, field="file"
            )
    except (NotConfigured, ConnectionFailed) as exc:
        raise StorageUnavailable(str(exc)) from exc

    return IngestResponse(
        artifact_id=result.artifact.id,
        name=result.artifact.name,
        side=result.artifact.side,
        chunks=result.chunks,
        embedding_model=result.artifact.embedding_model,
        embedding_minutes=result.embedding_minutes,
        slow=result.embedding_minutes > services.WARN_MINUTES,
    )
