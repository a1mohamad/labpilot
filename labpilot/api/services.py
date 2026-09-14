from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterator, Sequence

import psycopg

from labpilot.api.contracts import Artifact, Comparison, Ingested
from labpilot.api.errors import (
    ArtifactChanged,
    ArtifactSidesClash,
    ArtifactsTooLargeToCompare,
    EmbeddingUnavailable,
    EmptyArtifact,
    GenerationUnavailable,
    InvalidQuestion,
    UnknownArtifactId,
    UnreadableUpload,
)
from labpilot.api.reranking import rank as _rank
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
    OUTLINE_BUDGET,
    PROMPT_BUDGET,
    REPORT,
    REPORT_MAX_TOKENS,
    build_prompt,
    reserve,
)
from labpilot.rerank import RERANK_TOP_N, SKIP, Ranking
from labpilot.retrieval import LABEL_TOKENS, select, should_rerank
from labpilot.sources import Source, walk
from labpilot.store import (
    SEARCH_LIMIT,
    ArtifactRecord,
    ChunkRecord,
    ModelMismatch,
    SearchHit,
    StoredArtifact,
    StoredChunk,
    UnknownArtifact,
    measure,
    read_chunks,
    search,
    write_artifact,
)
from labpilot.tokens import CHARS_PER_TOKEN, estimate_tokens

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

# How many chunks survive the vector path when NO reranker ran.
#
# A SEPARATE number from RERANK_TOP_N on purpose, and the distinction was
# missing from CLAUDE.md until 2026-09-14: one asks how many to send after a
# reranker ordered them, the other how many to send when none did. The two
# paths have different recall curves, so one number cannot serve both.
#
# UNMEASURED, like every other top_n here - slice 8 owns them all.
VECTOR_TOP_N = 25


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
    chunks: tuple[Chunk, ...],
    *,
    question: str,
    totals: dict[str, int] | None = None,
) -> tuple[str, tuple[Chunk, ...]]:
    overhead = reserve(chunks, question=question, instructions=REPORT)
    room = PROMPT_BUDGET - overhead
    selected = select(chunks, budget=room) if room > 0 else ()
    prompt = build_prompt(
        chunks,
        selected,
        question=question,
        instructions=REPORT,
        totals=totals,
    )

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


# How many chunks survive the vector path when NO reranker ran.
#
# A SEPARATE number from RERANK_TOP_N on purpose, and the distinction was
# missing from CLAUDE.md until 2026-09-14: one asks how many to send after a
# reranker ordered them, the other how many to send when none did. The two
# paths have different recall curves, so one number cannot serve both.
#
# UNMEASURED, like every other top_n here - slice 8 owns them all.
VECTOR_TOP_N = 25


def ask(
    conn: psycopg.Connection,
    a_id: str,
    b_id: str,
    *,
    question: str,
    client: LLMClient,
) -> Comparison:
    """Answer a question about two STORED artifacts.

    The ladder, and step 1 is the one that keeps being under-weighted:

        1  do A and B TOGETHER fit?  -> read every row back, STUFF, and neither
           embed nor search nor rerank runs at all
        2  otherwise search per side, gate, rerank per side, never merged

    Stuffing is not a shortcut. When the corpus fits, retrieval is not neutral
    but HARMFUL: a bad retriever can hide the very line the report needed.
    """
    if not question.strip():
        raise InvalidQuestion("question must not be empty")

    sides = _sides(conn, a_id, b_id)

    if _fits(sides, question=question):
        chunks, totals = _stuffed(conn, sides), None
    else:
        chunks = _retrieved(conn, sides, question=question)
        totals = {side: found.chunks for side, found in sides.items()}

    prompt, selected = _prompt(chunks, question=question, totals=totals)

    try:
        result = client.generate(prompt, max_tokens=REPORT_MAX_TOKENS)
    except AllFreeTiersExhausted as exc:
        raise GenerationUnavailable(
            "every free tier failed", attempts=exc.attempts
        ) from exc

    return Comparison(result=result, chunks=chunks, selected=selected, prompt=prompt)


def _sides(
    conn: psycopg.Connection, a_id: str, b_id: str
) -> dict[Side, StoredArtifact]:
    """Measure both artifacts, and take each one's side from the STORED row.

    Not from the request slot. `_artifact_id` is `f"{side}-{hash}"`, so the
    side is already baked into the id and the same file uploaded twice is two
    corpora - letting the slot disagree with the row would be two sources of
    truth for one fact.
    """
    found: dict[Side, StoredArtifact] = {}
    for artifact_id in (a_id, b_id):
        try:
            stored = measure(conn, artifact_id)
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc

        if stored.artifact.side in found:
            raise ArtifactSidesClash(
                f"both {a_id!r} and {b_id!r} are side "
                f"{stored.artifact.side!r}: a comparison needs one of each"
            )
        found[stored.artifact.side] = stored

    return found


def _fits(sides: dict[Side, StoredArtifact], *, question: str) -> bool:
    """Would both artifacts fit the prompt whole, without reading a single row?

    Deliberately CONSERVATIVE, and it errs toward searching. The outline is
    charged at its full OUTLINE_BUDGET even though the ladder usually renders
    far less, because the real cost cannot be known without the headers - and
    the headers are the thing this check exists to avoid fetching.

    So a corpus near the line is searched when it could have been stuffed.
    That is the safe direction: searching still answers, while a wrong `yes`
    means reading ~14MB over the wire to discover it did not fit.
    """
    evidence = sum(
        math.ceil(found.characters / CHARS_PER_TOKEN) + found.chunks * LABEL_TOKENS
        for found in sides.values()
    )
    fixed = estimate_tokens(f"{REPORT.header}{REPORT.closing}{question}")

    return evidence + fixed + OUTLINE_BUDGET <= PROMPT_BUDGET


def _stuffed(
    conn: psycopg.Connection, sides: dict[Side, StoredArtifact]
) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for side, found in sides.items():
        chunks.extend(
            _as_chunk(stored, side, found.artifact.id)
            for stored in read_chunks(conn, found.artifact.id)
        )

    return tuple(chunks)


def _retrieved(
    conn: psycopg.Connection, sides: dict[Side, StoredArtifact], *, question: str
) -> tuple[Chunk, ...]:
    """Search, gate and rerank PER SIDE - never merged.

    Merged would halve the rerank cost and hand one call 100 documents, but it
    also lets one side take every slot. Per side makes coverage STRUCTURAL
    rather than a rule something downstream has to honour.
    """
    chunks: list[Chunk] = []
    for side, found in sides.items():
        artifact = found.artifact
        vector = _embed_question(question, model=artifact.embedding_model)

        # measure() and search() are two round trips, and write_artifact
        # deletes then re-inserts - so a re-ingest with a different embedder
        # between them moves the model under a request already in flight.
        # Rare, real, and the only thing that makes ModelMismatch reachable
        # when we pass the model FROM the row search() checks it against.
        try:
            hits = search(
                conn,
                artifact.id,
                vector,
                model=artifact.embedding_model,
                limit=SEARCH_LIMIT,
            )
        except ModelMismatch as exc:
            raise ArtifactChanged(
                f"{artifact.id!r} was re-ingested with a different embedder "
                f"while this comparison was running: ask again"
            ) from exc

        chunks.extend(
            _as_chunk(hit, side, artifact.id) for hit in _best(question, hits)
        )

    return tuple(chunks)


def _best(
    question: str, hits: tuple[SearchHit, ...], *, rank: Callable[..., Ranking] = _rank
) -> list[SearchHit]:
    """Gate, rerank, and map POSITIONS back to hits.

    THE TWO NUMBER SPACES MEET HERE, and they look identical:

        SearchHit.chunk_index   an ID in the corpus
        Ranking.order           POSITIONS into the list we just passed

    `hits[position]` is right. Treating a position as an id cites the wrong
    file and line with full confidence, which is why
    tests/integration/test_retrieval_to_rerank.py numbers its ids from 100.

    And the cut happens AFTER, never by handing `top_n` down: skip() truncates
    to whatever it is given, so a chain that fell through to it would return
    RERANK_TOP_N chunks - a number calibrated for a path that did not run. The
    Ranking says which happened, so we cut on the visible fact.
    """
    if not hits:
        return []
    if not should_rerank([hit.score for hit in hits]):
        return list(hits[:VECTOR_TOP_N])

    ranking = rank(question, [hit.text for hit in hits], top_n=None)
    kept = VECTOR_TOP_N if ranking.model == SKIP else RERANK_TOP_N

    return [hits[position] for position in ranking.order[:kept]]


def _embed_question(question: str, *, model: str) -> tuple[float, ...]:
    """One query embed PER ARTIFACT'S OWN MODEL, with task="query".

    Two artifacts may hold two different embedders, because ingest_artifact
    picks one per artifact. Mixing is ALLOWED and costs one extra query embed
    and nothing else, because A's vectors never meet B's vectors - the
    comparison happens as TEXT, read by the model. Refusing it would block a
    legitimate pair and force an expensive re-ingest to fix.

    `task="query"` is not decoration: a question is a REQUEST and a chunk is a
    STATEMENT, and the providers that model that asymmetry rank measurably
    better for it.
    """
    for embedder in MIGRATION:
        if embedder.model == model:
            try:
                return embedder.embed([question], task="query").vectors[0]
            except EmbeddingError as exc:
                raise EmbeddingUnavailable(f"{embedder.name}: {exc}") from exc

    raise EmbeddingUnavailable(
        f"this corpus was embedded with {model!r}, which is no longer in "
        f"MIGRATION, so its question cannot be put in the same space"
    )


def _as_chunk(stored: SearchHit | StoredChunk, side: Side, artifact_id: str) -> Chunk:
    """store/ -> ingest/, and entry is the only layer allowed to do it.

    Neither StoredChunk nor SearchHit carries `side` or `artifact_id`, because
    store/ is an adapter and may not import ingest/. The caller knows both: it
    passed the id, and the side came from the artifact row.
    """
    return Chunk(
        text=stored.text,
        source=stored.source,
        start_line=stored.start_line,
        end_line=stored.end_line,
        side=side,
        artifact_id=artifact_id,
        chunk_index=stored.chunk_index,
        header=stored.header,
    )
