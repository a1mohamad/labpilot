from __future__ import annotations

from collections.abc import Iterator

from labpilot.api.contracts import Artifact, Comparison
from labpilot.api.errors import (
    ArtifactsTooLargeToCompare,
    EmptyArtifact,
    GenerationUnavailable,
    InvalidQuestion,
    UnreadableUpload,
)
from labpilot.ingest import (
    Chunk,
    LoaderError,
    NotUtf8Text,
    Side,
    chunk_bytes,
    chunk_file,
)
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import (
    PROMPT_BUDGET,
    REPORT,
    REPORT_MAX_TOKENS,
    build_prompt,
    reserve,
)
from labpilot.retrieval import select
from labpilot.sources import Source, walk
from labpilot.tokens import estimate_tokens


def compare(
    a: Artifact, b: Artifact, *, question: str, client: LLMClient
) -> Comparison:
    if not question.strip():
        raise InvalidQuestion("question must not be empty")

    chunks = _cut(a, side="A", field="a") + _cut(b, side="B", field="b")
    prompt, selected = _prompt(chunks, question=question)

    try:
        result = client.generate(prompt, max_tokens=REPORT_MAX_TOKENS)
    except AllFreeTiersExhausted as exc:
        raise GenerationUnavailable(
            "every free tier failed", attempts=exc.attempts
        ) from exc

    return Comparison(result=result, chunks=chunks, selected=selected, prompt=prompt)


def _cut(artifact: Artifact, *, side: Side, field: str) -> tuple[Chunk, ...]:
    try:
        chunks = chunk_bytes(
            artifact.raw,
            source=artifact.name,
            side=side,
            artifact_id=artifact.name,
        )
    except LoaderError as exc:
        raise UnreadableUpload(f"{field} ({artifact.name}): {exc}") from exc
    if not chunks:
        raise EmptyArtifact(f"{field} ({artifact.name}) holds no text")

    return chunks


def _prompt(
    chunks: tuple[Chunk, ...], *, question: str
) -> tuple[str, tuple[Chunk, ...]]:
    overhead = reserve(chunks, question=question, instructions=REPORT)
    room = PROMPT_BUDGET - overhead
    selected = select(chunks, budget=room) if room > 0 else ()
    prompt = build_prompt(chunks, selected, question=question, instructions=REPORT)

    if not selected or estimate_tokens(prompt) > PROMPT_BUDGET:
        raise ArtifactsTooLargeToCompare(
            f"too large to compare: {len(chunks)} parts need {overhead} tokens "
            f"just to list, of a {PROMPT_BUDGET} token budget, so no artifact "
            f"text fits. Step 0 sends one outline line per part; use smaller "
            f"artifacts until Step 1 replaces it with a per-file outline"
        )

    return prompt, selected


def chunk_source(source: Source, *, side: Side) -> Iterator[Chunk]:
    for found in walk(source):
        try:
            pieces = chunk_file(
                found.path,
                side=side,
                artifact_id=source.name,
                source=found.relpath,
            )
        except NotUtf8Text:
            source.skip("not utf-8")
            continue
        except LoaderError:
            source.skip("unreadable document")
            continue
        except OSError:
            source.skip("unreadable file")
            continue

        yield from pieces
