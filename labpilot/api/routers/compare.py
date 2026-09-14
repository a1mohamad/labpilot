from __future__ import annotations

from fastapi import APIRouter, status

from labpilot.api import services
from labpilot.api.contracts import Comparison
from labpilot.api.dependencies import LLMClientDep
from labpilot.api.errors import StorageUnavailable
from labpilot.api.schemas import (
    AttemptOut,
    CitationOut,
    CitationReport,
    CompareRequest,
    CompareResponse,
    ErrorEnvelope,
    SideChunks,
)
from labpilot.ingest import Chunk
from labpilot.prompts import find_citations, resolve
from labpilot.store import ConnectionFailed, NotConfigured, connect

router = APIRouter(tags=["comparison"])

FAILURES: dict[int | str, dict] = {
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "model": ErrorEnvelope,
        "description": "An upload, or the whole body, is over its limit.",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorEnvelope,
        "description": "An upload is unreadable, unnamed, empty, or the "
        "question is blank.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorEnvelope,
        "description": "Every tier in the chain failed. `attempts` says why.",
    },
    # Both belong to the ask path, which takes artifact IDS. They are
    # documented here a step early on purpose: the contract is derived from the
    # ApiError hierarchy, so a status that exists and is undocumented makes
    # OpenAPI describe an endpoint that can surprise its caller.
    status.HTTP_404_NOT_FOUND: {
        "model": ErrorEnvelope,
        "description": "An artifact id is not stored.",
    },
    status.HTTP_409_CONFLICT: {
        "model": ErrorEnvelope,
        "description": "An artifact was re-ingested with a different embedder "
        "mid-request. Ask again.",
    },
}


@router.post(
    "/compare",
    responses=FAILURES,
    summary="Compare two stored artifacts and explain why their results diverge",
)
def compare(body: CompareRequest, client: LLMClientDep) -> CompareResponse:
    """Ask a question about two artifacts that are already stored.

    IDS, not files. Under the old shape every question re-chunked and
    re-embedded both sides - measured at about fifteen minutes per question for
    a FastAPI-sized repository. Ingest is paid once, at POST /artifacts, and
    what crosses the wire each turn is a question.

    The connection is opened HERE, as it is for /artifacts, because every
    function in store/ takes one - so the route is the layer that owns
    reaching the database and mapping the two ways that fails.
    """
    try:
        with connect() as conn:
            comparison = services.ask(
                conn, body.a, body.b, question=body.question, client=client
            )
    except (NotConfigured, ConnectionFailed) as exc:
        raise StorageUnavailable(str(exc)) from exc

    return _response(comparison)


def _response(comparison: Comparison) -> CompareResponse:
    result = comparison.result

    return CompareResponse(
        answer=result.text,
        model=result.model,
        tier=result.tier,
        finish_reason=result.finish_reason,
        attempts=[
            AttemptOut(tier=one.tier, model=one.model, error=one.error)
            for one in result.attempts
        ],
        chunks={side: _counts(comparison, side) for side in ("A", "B")},
        citations=_citations(result.text, comparison.chunks),
    )


def _counts(comparison: Comparison, side: str) -> SideChunks:
    """`n of m` for one side, where m is what the artifact HOLDS.

    On the search path `chunks` is only what retrieval returned, so counting
    it would report "25 of 25" for a corpus of 120 and the number that exists
    to prove the file was read would instead claim it was read whole.
    """
    read = sum(1 for chunk in comparison.chunks if chunk.side == side)
    held = (comparison.totals or {}).get(side, read)

    return SideChunks(
        total=held,
        sent=sum(1 for chunk in comparison.selected if chunk.side == side),
    )


def _citations(answer: str, chunks: tuple[Chunk, ...]) -> CitationReport:
    written = find_citations(answer)
    found = [
        CitationOut(
            chunk_id=chunk_id,
            quote=quote,
            source=hit.source,
            line=hit.line,
            text=hit.text,
            unique=hit.unique,
        )
        for chunk_id, quote in written
        if (hit := resolve(chunk_id, quote, chunks))
    ]

    return CitationReport(
        written=len(written), resolved=len(found), resolved_list=found
    )
