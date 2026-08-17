from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, UploadFile, status

from labpilot.api import services
from labpilot.api.contracts import Comparison
from labpilot.api.dependencies import LLMClientDep
from labpilot.api.schemas import (
    AttemptOut,
    CitationOut,
    CitationReport,
    CompareResponse,
    ErrorEnvelope,
    SideChunks,
)
from labpilot.api.uploads import read_artifact
from labpilot.ingest import Chunk
from labpilot.prompts import find_citations, resolve

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
}


@router.post(
    "/compare",
    response_model=CompareResponse,
    responses=FAILURES,
    summary="Compare two artifacts and explain why their results diverge",
)
def compare(
    a: UploadFile,
    b: UploadFile,
    question: Annotated[str, Form()],
    client: LLMClientDep,
) -> CompareResponse:
    comparison = services.compare(
        read_artifact(a, field="a"),
        read_artifact(b, field="b"),
        question=question,
        client=client,
    )

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
    return SideChunks(
        total=sum(1 for chunk in comparison.chunks if chunk.side == side),
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
