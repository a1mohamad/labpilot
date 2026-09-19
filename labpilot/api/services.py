from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from hashlib import sha256

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
from labpilot.retrieval import LABEL_TOKENS, score_fusion, select, should_rerank
from labpilot.sources import Source, walk
from labpilot.store import (
    SEARCH_LIMIT,
    ArtifactRecord,
    ChunkRecord,
    ModelMismatch,
    SearchHit,
    StoredArtifact,
    StoredChunk,
    StoreError,
    UnknownArtifact,
    bm25_search,
    measure,
    read_chunks,
    search,
    write_artifact,
)
from labpilot.tokens import CHARS_PER_TOKEN, estimate_tokens

logger = logging.getLogger(__name__)

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

# SMALL_CORPUS_CHUNKS WAS HERE AND IS DELETED - 2026-09-18.
#
# It routed any corpus under 500 chunks to Google first, on the v2 finding that
# "Google retrieves best where vector search is already easy". That rested on
# THREE corpora. Re-measured on six, against `gemini-embedding-001` (the model
# that matters after the MIGRATION fix in embed/registry.py):
#
#     corpus      chunks  codestral  gemini-001
#     websocket       78    0.668      0.530     codestral +0.138
#     quora           82    0.608      0.674     google    +0.066
#     disaster       108    0.753      0.760     google    +0.006
#     titanic        118    0.594      0.537     codestral +0.057
#     requests       335    0.646      0.650     google    +0.004
#     lung           628    0.587      0.569     codestral +0.019
#
# THREE WINS EACH, and net codestral ahead by 0.023 MRR - about half a query on
# a 20-query fixture, which is BELOW what these fixtures can resolve. So the
# rule bought no measurable quality, while costing:
#
#   19x slower than codestral at every size (4.1 min against 0.21 at 500)
#   it tripped its own WARN_MINUTES = 2.0, so the router chose an embedder the
#     UI then had to apologise for
#   1,000 TEXTS a day, exhausted by a single 943-chunk run while measuring this
#
# A rule that exists to buy quality, and buys none, is deleted rather than
# retuned. MIGRATION's own order now decides, and codestral leads it on
# measured recall - 19 of 20 corpora against mistral-embed.


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

    return _store(conn, chunks, artifact_id=artifact_id, name=name, side=side)


def ingest_source(conn: psycopg.Connection, source: Source, *, side: Side) -> Ingested:
    """A whole folder, archive or repository, stored as ONE artifact.

    The walk counts what it skipped rather than dropping it - a repository is
    the case where one unreadable file used to abort the entire ingest, twice,
    silently, because a generator stops at the first raise.
    """
    chunks = tuple(chunk_source(source, side=side))
    if not chunks:
        raise EmptyArtifact(f"{source.name} holds no text we can read")

    artifact_id = _source_id(chunks, side)
    chunks = tuple(replace(chunk, artifact_id=artifact_id) for chunk in chunks)

    return _store(conn, chunks, artifact_id=artifact_id, name=source.name, side=side)


def _store(
    conn: psycopg.Connection,
    chunks: Sequence[Chunk],
    *,
    artifact_id: str,
    name: str,
    side: Side,
) -> Ingested:
    """Pick an embedder, embed, and write - shared by both ingest doors.

    Extracted when the repository door arrived rather than duplicated, because
    the two doors differ ONLY in how they get chunks. Slice 3 was bitten twice
    by two doors drifting apart on exactly this kind of shared step.
    """
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


def _source_id(chunks: Sequence[Chunk], side: Side) -> str:
    """The CONTENT decides the id, as it does for a single file.

    Hashed from what was really read - each file's path and text - rather than
    from the archive's bytes, so the same repository arriving as a zip and as a
    git URL is ONE artifact and re-ingesting replaces it.
    """
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.source.encode("utf-8"))
        digest.update(chunk.text.encode("utf-8"))

    return f"{side}-{digest.hexdigest()[:16]}"


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

    THERE IS NO LONGER A SPECIAL CASE FOR SMALL CORPORA. One used to send
    anything under 500 chunks to Google first; it was re-measured on six
    corpora in slice 8 v3, found to buy no resolvable quality, and deleted -
    the numbers are above the constants at the top of this file.
    """
    order = candidates
    if (
        order[0].embedding_minutes(tokens=tokens, chunks=chunks)
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


def _newest_owner(source: Source, *, side: Side) -> dict[str, str]:
    """For every distinct chunk text, the NEWEST file that holds it.

    A repository really does hold the same content several times, and the copies
    are the ones our own fixtures had to exclude by hand: `lung` was 34.8%
    duplicate chunks from mlflow artifact copies, `pydantic` 6.6% from mypy
    outputs, and the user's `titanic` folder holds THREE versions of one
    notebook plus Jupyter's auto-save - 39.1% duplicate text, measured.

    NEWEST, not first, and that is the whole point. Sorted-path order would have
    kept `titanic_V2.ipynb` over `titanic_analysisV2.ipynb`, so a divergence
    report would compare the paper against code the user replaced months ago -
    confidently, with a citation. For a tool whose job is explaining why two
    things differ, answering from a stale copy is the worst failure it has.

    IDS STILL COME FROM PATH ORDER. mtime decides only WHICH copy survives,
    never the order chunks are numbered in: a fresh clone gives every file the
    same mtime, so ordering by it would make chunk ids differ between machines -
    the determinism `_paths` sorts for.

    The cost is one extra chunking pass. MEASURED: 0.9s for pytest's 10,064
    chunks, against an embed of several minutes. Only hashes are kept, so the
    streaming rule is untouched.
    """
    owners: dict[str, tuple[float, str]] = {}
    for found in walk(source):
        try:
            pieces = chunk_file(
                found.path, side=side, artifact_id=source.name, source=found.relpath
            )
            mtime = found.path.stat().st_mtime
        except (LoaderError, OSError):
            continue

        for piece in pieces:
            key = sha256(piece.text.encode("utf-8")).hexdigest()
            best = owners.get(key)
            if best is None or mtime > best[0]:
                owners[key] = (mtime, found.relpath)
    return {key: relpath for key, (_, relpath) in owners.items()}


def chunk_source(source: Source, *, side: Side) -> Iterator[Chunk]:
    owners = _newest_owner(source, side=side)
    seen: set[str] = set()
    index = 0
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

        for piece in pieces:
            # A chunk this file does not OWN is a copy of one we are keeping
            # elsewhere, and a second copy buys nothing: it cannot answer a
            # question the first cannot, and it spends embedding budget, a
            # storage row and a slot in every future search window.
            #
            # The cost is real and small: two modules that genuinely define the
            # same thing are now cited once, at the newest of them.
            key = sha256(piece.text.encode("utf-8")).hexdigest()
            if owners.get(key) != found.relpath or key in seen:
                source.skip("duplicate of a newer copy")
                continue
            seen.add(key)

            # chunk_index restarts at 0 in every file, because chunk_file
            # numbers what IT produced. The chunks table's primary key is
            # (artifact_id, chunk_index), so a repository of twenty files would
            # collide on the second one - and prompt ids are positional, so
            # even without a database two files would both claim B-0.
            yield replace(piece, chunk_index=index)
            index += 1


# How many chunks survive the vector path when NO reranker ran.
#
# A SEPARATE number from RERANK_TOP_N on purpose, and the distinction was
# missing from CLAUDE.md until 2026-09-14: one asks how many to send after a
# reranker ordered them, the other how many to send when none did. The two
# paths have different recall curves, so one number cannot serve both.
#
# 30 -> 15 ON 2026-09-19, AND THE 30 WAS A UNIT ERROR, not a measurement.
#
# The experiment counts chunks in the WHOLE PROMPT. Both constants here are
# PER SIDE, and the product sends two sides, so the prompt holds 2x the
# constant and the conversion is experiment_N / 2. It was applied to
# RERANK_TOP_N (best at experiment N=20 -> 10 per side) and NOT to this one,
# which shipped 30 - a 60-chunk prompt, a value no run ever tested.
#
# MEASURED, 18 corpora, 8 Python, 383 questions, flash-lite:
#
#     experiment N=10  0.245     -> 5 per side
#     experiment N=20  0.462     -> 10
#     experiment N=30  0.512     -> 15   <- best, and this is the number
#
# The knee is sharp. On 3.1-flash-lite over the four corpora carrying every
# value, the first 10 chunks past N=10 buy +0.182 and the next EIGHTY buy
# +0.091 - ten times less per chunk. Past a 20-chunk prompt the two-sided
# total also clears Gemma's 16,000-token input cap, which costs 57,600 calls a
# day, so "send more" is not free even where it still helps slightly.
#
# PER SIDE, so 15 is 30 chunks ~ 7,100 tokens at the measured 236/chunk,
# against PROMPT_BUDGET 26,000. docs/slice8v3/DECISIONS.md row 18.
VECTOR_TOP_N = 15

# How many of the searched chunks the RERANKER SEES.
#
# A THIRD number, and a different question from both of the others:
#
#   SEARCH_LIMIT   50   what search returns          per side
#   RERANK_WINDOW  20   what the reranker reads      per side   <- this
#   RERANK_TOP_N   10   what survives reranking      per side
#   VECTOR_TOP_N   15   what we send when NO reranker ran
#
# MEASURED 2026-09-18, slice 8 v3: six windows on 5 corpora that are 100%
# Python, 89 to 9,846 chunks, flash-lite. Mean MRR gain over vector alone:
#
#   w10 +0.095   w20 +0.090   w30 +0.084   w50 +0.053   w5 +0.041
#
# THE SHIPPED w50 IS NEARLY HALF AS GOOD AS THE BEST. w10, w20 and w30 are
# indistinguishable - +1.84, +1.76 and +1.67 queries, a spread of 0.17 against
# a 1.5-query bar - so the pick inside that band is made on cost and reach, not
# on score: 20 is the middle of the flat region and costs fewer tokens per call
# than 30, so more rerank tiers stay reachable.
#
# It supersedes v2's per-tier window argument (CLAUDE.md 14.3), which existed so
# Voyage could be served at 30 while others took 50. At 20 EVERY tier serves
# EVERY corpus, so there is nothing left for a per-tier rule to arbitrate.
# rerank/'s own max_documents stays as the lower-level guard.
#
# Note the window sits ABOVE VECTOR_TOP_N (20 against 15) and that is not a
# contradiction: this is what the reranker READS, and VECTOR_TOP_N is what we
# SEND when it never ran. Reading more than we would have sent is the point -
# the reranker earns its place by reordering candidates the degraded path
# would have dropped.
#
# What does sit BELOW VECTOR_TOP_N is RERANK_TOP_N, 10 against 15: the two are
# different paths with different recall curves, and the reranked one is
# sharper, so it can cut harder.
#
# (This paragraph said "it sits BELOW VECTOR_TOP_N" until 2026-09-19, which was
# true only while VECTOR_TOP_N was still the unit-error 30.)
# docs/slice8v3/DECISIONS.md row 10, FINDINGS H12.
RERANK_WINDOW = 20


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

    return Comparison(
        result=result,
        chunks=chunks,
        selected=selected,
        prompt=prompt,
        totals=totals,
    )


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
            _as_chunk(hit, side, artifact.id)
            for hit in _best(question, _fused(conn, artifact.id, question, hits))
        )

    return tuple(chunks)


def _fused(
    conn: psycopg.Connection,
    artifact_id: str,
    question: str,
    dense: tuple[SearchHit, ...],
) -> tuple[SearchHit, ...]:
    """Add the KEYWORD channel and fuse. Always on, never conditional.

    v2 shipped the rule *"fuse below r@50 ~ 0.95 and not above"*, and v3 threw
    it out for a reason no amount of measuring could fix: **r@50 needs ground
    truth, and a user's repository has none, ever.** The condition can be
    evaluated on a benchmark and never at run time, and no proxy stands in for
    it - pydantic at 9,846 chunks is saturated while geo at 729 is not.

    So the channel is permanently on, which is only safe because of what was
    measured over 20 corpora and 423 queries: it gains a query or more on 5
    corpora and loses a query or more on NONE.

    Vectors are good at meaning, keywords are good at names, and code is mostly
    names. `D2` is the case that pays for this: the constant CLIP_NORM = 1.5
    sits at place 46 on cosine and place 4 on BM25.

    BM25, never ts_rank: Postgres hands ts_rank ONE document, so it cannot know
    document frequency and has no IDF at all. We compute BM25 in Python over
    the stored lexemes, which is the 4-5 extra round trips this costs.
    """
    try:
        sparse = bm25_search(conn, artifact_id, question, limit=SEARCH_LIMIT)
    except StoreError:
        # DEGRADE, LOUDLY. The keyword channel is worth +8.7 queries out of
        # 423; the vector channel is worth the whole answer. A keyword fault
        # must never take a working search down with it - the same shape as
        # skip() when no reranker is available.
        logger.warning(
            "keyword channel failed for %s, answering on vector alone",
            artifact_id,
            exc_info=True,
        )
        return dense

    if not sparse:
        return dense

    by_index = {hit.chunk_index: hit for hit in (*sparse, *dense)}
    order = score_fusion(
        [(hit.chunk_index, hit.score) for hit in dense],
        [(hit.chunk_index, hit.score) for hit in sparse],
    )

    # Back to SEARCH_LIMIT: the union of two 50-hit channels can reach 100, and
    # everything downstream - RERANK_WINDOW, VECTOR_TOP_N - is calibrated
    # against a 50-candidate window per side.
    return tuple(by_index[index] for index in order[:SEARCH_LIMIT])


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

    window = hits[:RERANK_WINDOW]
    ranking = rank(question, [hit.text for hit in window], top_n=None)

    # The DEGRADED path reads `hits`, never `window`. A tier that declined has
    # not narrowed anything, so narrowing for it would throw away chunks the
    # vector path had already paid for - and VECTOR_TOP_N is calibrated on the
    # full list.
    if ranking.model == SKIP:
        return list(hits[:VECTOR_TOP_N])

    # POSITIONS index the list we PASSED, which is `window`. Today `hits`
    # would give the identical element, because `window` is a PREFIX of it and
    # every position is inside the window - a mutation swapping the two broke
    # nothing, which is the honest state and is recorded rather than tested.
    # We index `window` because it is the list we handed over, and that stays
    # right if the window is ever chosen rather than truncated.
    return [window[position] for position in ranking.order[:RERANK_TOP_N]]


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
