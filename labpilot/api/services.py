from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator, Sequence

import psycopg

from labpilot.api.contracts import Artifact, Comparison, Ingested
from labpilot.api.errors import (
    ArtifactsTooLargeToCompare,
    EmbeddingUnavailable,
    EmptyArtifact,
    GenerationUnavailable,
    InvalidQuestion,
    UnreadableUpload,
)
from labpilot.embed import (
    MIGRATION,
    EmbeddingError,
    HTTPEmbedder,
    by_speed,
    embed_batches,
)
from labpilot.ingest import (
    Chunk,
    LoaderError,
    LooksGenerated,
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
from labpilot.store import ArtifactRecord, ChunkRecord, write_artifact
from labpilot.tokens import estimate_tokens

# How long an ingest may take before we stop optimising for QUALITY and start
# optimising for TIME. NOT a refusal: past this line the same list is sorted by
# speed instead of by strength, and a slow model is still used when every fast
# one is spent - the user is shown the estimate and asked first.
EMBEDDING_MINUTES_BUDGET = 6.0

# When to STOP and ask the user. Deliberately far lower, because embedding is
# one stage of several: measured, a full report is another ~52s today and
# roughly ten LLM calls once the agent exists. A 2-minute embed is already a
# 3-4 minute answer. THIS NUMBER IS A GUESS - slice 8 owes an end-to-end
# measurement, and only that can set it honestly.
WARN_MINUTES = 2.0


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


def ingest_artifact(
    conn: psycopg.Connection,
    raw: bytes,
    *,
    name: str,
    side: Side,
    field: str = "artifact",
) -> Ingested:
    """Turn an uploaded file into rows in pgvector.

    Entry is the only layer allowed to import ingest/, embed/ AND store/, so
    the translation between their three vocabularies lives here by the layering
    rule rather than by preference:

        Chunk (ingest) + Vector (embed) -> ChunkRecord (store)

    The connection is passed IN, matching write_artifact and search. So a
    failure to reach the database happens in the caller, never here.
    """
    artifact_id = _artifact_id(raw, side)
    chunks = _cut_bytes(raw, name=name, side=side, artifact_id=artifact_id, field=field)

    tokens = sum(estimate_tokens(chunk.embed_text) for chunk in chunks)
    embedder, minutes = _pick_embedder(tokens=tokens, chunks=len(chunks))
    artifact = ArtifactRecord(
        id=artifact_id,
        name=name,
        side=side,
        embedding_model=embedder.model,
        dim=embedder.dim,
    )

    try:
        written = write_artifact(conn, artifact, _records(embedder, chunks))
    except EmbeddingError as exc:
        raise EmbeddingUnavailable(f"{embedder.name}: {exc}") from exc
    return Ingested(artifact=artifact, chunks=written, embedding_minutes=minutes)


def _artifact_id(raw: bytes, side: Side) -> str:
    """The CONTENT decides the id, so re-ingesting the same file replaces it.

    write_artifact deletes before inserting, so a stable id makes ingest
    idempotent: upload the same paper twice and you get one corpus, not two.
    The side is part of the id because one file can legitimately be both the
    reference and the subject.
    """
    return f"{side}-{hashlib.sha256(raw).hexdigest()[:16]}"


def _pick_embedder(
    *, tokens: int, chunks: int, candidates: Sequence[HTTPEmbedder] = MIGRATION
) -> tuple[HTTPEmbedder, float]:
    """ONE list, sorted two ways - by strength normally, by speed when slow.

    MIGRATION is already the strength order. If its best model would take
    longer than the budget, the SAME list is re-sorted by speed. Nothing is
    ever dropped, so the walk cannot dead-end; only a model's place moves. A
    two-pool version was considered first and was wrong for exactly that
    reason: two fast models, both spent, and nowhere left to go.

    A model that cannot finish TODAY reports infinite time and is skipped,
    which is how Cloudflare's daily neuron budget removes BGE from a large
    corpus without needing a second mechanism.
    """
    order = candidates
    if (
        candidates[0].embedding_minutes(tokens=tokens, chunks=chunks)
        > EMBEDDING_MINUTES_BUDGET
    ):
        order = by_speed(tokens=tokens, chunks=chunks, candidates=candidates)

    for embedder in order:
        minutes = embedder.embedding_minutes(tokens=tokens, chunks=chunks)
        if minutes != math.inf:
            return embedder, minutes

    raise EmbeddingUnavailable(
        f"no embedder can ingest {chunks} chunks ({tokens} tokens) today"
    )


def _records(embedder: HTTPEmbedder, chunks: Sequence[Chunk]) -> Iterator[ChunkRecord]:
    """Chunk + vector -> ChunkRecord, one batch at a time.

    A GENERATOR on purpose. 2,000 vectors of 1,536 floats held as Python lists
    is ~73MB against a 512MB box that is also serving the API; yielding per
    batch keeps the peak near 5MB. write_artifact consumes this INSIDE one
    transaction, so streaming and atomicity do not conflict - streaming is
    about Python objects, the transaction is about the database. Either all
    2,000 rows land or none do.
    """
    texts = [chunk.embed_text for chunk in chunks]
    index = 0
    for batch in embed_batches(embedder, texts):
        for vector in batch.vectors:
            chunk = chunks[index]
            yield ChunkRecord(
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                header=chunk.header,
                source=chunk.source,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                vector=vector,
            )
            index += 1


def _cut_bytes(
    raw: bytes, *, name: str, side: Side, artifact_id: str, field: str
) -> tuple[Chunk, ...]:
    """The loader-error mapping, shared by both doors.

    Extracted so the upload path and the ingest path cannot drift apart: the
    same bad .ipynb must become the same 422 whichever door it arrives at.
    Slice 3 was bitten twice by exactly that - one door was fixed and the
    other silently mangled notebooks.
    """
    try:
        chunks = chunk_bytes(raw, source=name, side=side, artifact_id=artifact_id)
    except LoaderError as exc:
        raise UnreadableUpload(f"{field} ({name}): {exc}") from exc
    if not chunks:
        raise EmptyArtifact(f"{field} ({name}) holds no text")

    return chunks


def _cut(artifact: Artifact, *, side: Side, field: str) -> tuple[Chunk, ...]:

    return _cut_bytes(
        artifact.raw,
        name=artifact.name,
        side=side,
        artifact_id=artifact.name,
        field=field,
    )


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
        except LooksGenerated:
            source.skip("generated or minified")
            continue
        except LoaderError:
            source.skip("unreadable document")
            continue
        except OSError:
            source.skip("unreadable file")
            continue

        yield from pieces
