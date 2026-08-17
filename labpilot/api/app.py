from __future__ import annotations

from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, UploadFile

from labpilot.api.contracts import (
    AttemptOut,
    CitationOut,
    CitationReport,
    CompareResponse,
    ExhaustedDetail,
    SideChunks,
)
from labpilot.ingest import Chunk, Side, chunk_text
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult
from labpilot.prompts import (
    PROMPT_BUDGET,
    REPORT,
    REPORT_MAX_TOKENS,
    build_prompt,
    find_citations,
    reserve,
    resolve,
)
from labpilot.retrieval import select

MAX_UPLOAD_BYTES = 1_000_000

HTTP_UNPROCESSABLE = 422
HTTP_TOO_LARGE = 413
HTTP_UNAVAILABLE = 503

load_dotenv()

app = FastAPI(title="LabPilot", version="0.1.0")


def get_client() -> LLMClient:
    return LLMClient()


@app.post("/compare", response_model=CompareResponse)
def compare(
    a: UploadFile,
    b: UploadFile,
    question: Annotated[str, Form()],
    client: Annotated[LLMClient, Depends(get_client)],
) -> CompareResponse:
    if not question.strip():
        raise HTTPException(HTTP_UNPROCESSABLE, "question must not be empty")

    chunks = _chunks(a, side="A", field="a") + _chunks(b, side="B", field="b")

    room = PROMPT_BUDGET - reserve(chunks, question=question, instructions=REPORT)
    picked = select(chunks, budget=room)
    prompt = build_prompt(chunks, picked, question=question, instructions=REPORT)

    try:
        result = client.generate(prompt, max_tokens=REPORT_MAX_TOKENS)
    except AllFreeTiersExhausted as exc:
        raise HTTPException(
            HTTP_UNAVAILABLE,
            ExhaustedDetail(
                message="every free tier failed",
                attempts=_attempts(exc.attempts),
            ).model_dump(),
        ) from exc

    return _response(result, chunks, picked)


def _chunks(upload: UploadFile, *, side: Side, field: str) -> tuple[Chunk, ...]:
    name, text = _read(upload, field)
    chunks = chunk_text(text, source=name, side=side, artifact_id=name)
    if not chunks:
        raise HTTPException(HTTP_UNPROCESSABLE, f"{field} ({name}) holds no text")

    return chunks


def _read(upload: UploadFile, field: str) -> tuple[str, str]:
    name = Path(upload.filename or "").name
    if not Path(name).suffix:
        raise HTTPException(
            HTTP_UNPROCESSABLE,
            f"{field} needs a filename with an extension: the extension "
            f"chooses the splitter, and without one the file is cut blindly",
        )

    if upload.size is not None and upload.size > MAX_UPLOAD_BYTES:
        raise _too_large(field, name, upload.size)

    raw = upload.file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise _too_large(field, name, len(raw))

    try:
        return name, raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            HTTP_UNPROCESSABLE, f"{field} ({name}) is not UTF-8 text"
        ) from exc


def _too_large(field: str, name: str, size: int) -> HTTPException:
    return HTTPException(
        HTTP_TOO_LARGE,
        f"{field} ({name}) is {size} bytes, over the {MAX_UPLOAD_BYTES} byte limit",
    )


def _response(
    result: LLMResult, chunks: tuple[Chunk, ...], picked: tuple[Chunk, ...]
) -> CompareResponse:
    return CompareResponse(
        answer=result.text,
        model=result.model,
        tier=result.tier,
        finish_reason=result.finish_reason,
        attempts=_attempts(result.attempts),
        chunks={side: _counts(chunks, picked, side) for side in ("A", "B")},
        citations=_citations(result.text, chunks),
    )


def _attempts(attempts) -> list[AttemptOut]:
    return [
        AttemptOut(tier=one.tier, model=one.model, error=one.error) for one in attempts
    ]


def _counts(
    chunks: tuple[Chunk, ...], picked: tuple[Chunk, ...], side: str
) -> SideChunks:
    return SideChunks(
        total=sum(1 for chunk in chunks if chunk.side == side),
        sent=sum(1 for chunk in picked if chunk.side == side),
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
