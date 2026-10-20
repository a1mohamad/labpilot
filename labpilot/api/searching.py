from __future__ import annotations

import logging
from collections.abc import Callable

import psycopg

from labpilot.api.errors import (
    ArtifactChanged,
    EmbeddingUnavailable,
)
from labpilot.api.reading import as_chunk
from labpilot.api.reranking import rank as _rank
from labpilot.embed import (
    MIGRATION,
    EmbeddingError,
)
from labpilot.ingest import (
    Chunk,
    Side,
)
from labpilot.rerank import RERANK_TOP_N, SKIP, Ranking
from labpilot.retrieval import score_fusion, should_rerank
from labpilot.store import (
    SEARCH_LIMIT,
    ModelMismatch,
    SearchHit,
    StoredArtifact,
    StoreError,
    bm25_search,
    search,
)

logger = logging.getLogger(__name__)

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


def retrieved_chunks(
    conn: psycopg.Connection, sides: dict[Side, StoredArtifact], *, question: str
) -> tuple[Chunk, ...]:
    """Search, gate and rerank PER SIDE - never merged.

    Merged would halve the rerank cost and hand one call 100 documents, but it
    also lets one side take every slot. Per side makes coverage STRUCTURAL
    rather than a rule something downstream has to honour.
    """
    chunks: list[Chunk] = []
    for side in sides:
        artifact = sides[side].artifact
        hits = _searched(conn, sides, side=side, text=question)
        chunks.extend(
            as_chunk(hit, side, artifact.id) for hit in rerank_and_cut(question, hits)
        )

    return tuple(chunks)


def retrieve_query(
    conn: psycopg.Connection,
    sides: dict[Side, StoredArtifact],
    *,
    side: Side,
    text: str,
) -> tuple[Chunk, ...]:
    artifact = sides[side].artifact
    hits = _searched(conn, sides, side=side, text=text)
    return tuple(as_chunk(hit, side, artifact.id) for hit in hits)


def rank_pile(
    question: str,
    pile: tuple[Chunk, ...],
    *,
    rank: Callable[..., Ranking] = _rank,
) -> tuple[Chunk, ...]:
    if not pile:
        return ()
    window = pile[:RERANK_WINDOW]
    ranking = rank(question, [chunk.text for chunk in window], top_n=None)
    if ranking.model == SKIP:
        return pile[:VECTOR_TOP_N]

    return tuple(window[position] for position in ranking.order[:RERANK_TOP_N])


def _searched(
    conn: psycopg.Connection,
    sides: dict[Side, StoredArtifact],
    *,
    side: Side,
    text: str,
) -> tuple[SearchHit, ...]:
    artifact = sides[side].artifact
    vector = _embed_question(text, model=artifact.embedding_model)
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

    return _fused(conn, artifact.id, text, hits)


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


def rerank_and_cut(
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
