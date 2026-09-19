"""FUSION, AGAINST REAL ROWS - the join nothing was testing.

Two halves of this were covered and the seam between them was not:

    tests/integration/test_store_keyword.py   bm25_search against a real db
    tests/api/test_fusion_is_on.py            the wiring, with both channels stubbed

So `bm25_search` is known to work, and `_fused` is known to call something -
and nothing ran the real query builder against a really-ingested corpus. That
gap has a specific failure behind it: if the keyword channel returned NOTHING
on real rows, `_fused` takes its `if not sparse: return dense` branch, every
answer is vector-alone, every test above stays green, and the decision slice 8
v3 shipped after 20 corpora and 423 queries would be quietly doing nothing.

It is not a hypothetical shape. Slice 5 probed this exact query builder against
the real database and found THREE silent defects in it - a lexeme holding `:`
crashed it, a URL token reinstated the AND that scored 0 of 17, and re-stemming
an already-stemmed lexeme missed matches. Two of those return zero rows rather
than raising.

ONE TEST WAS WRITTEN HERE AND DELETED: "the fused window never exceeds
SEARCH_LIMIT". Mutating that cut fired `test_the_fused_window_never_exceeds_
what_search_returns` in tests/api/ and NOT this file - so it was a second copy
of a guard that already exists, and a new corpus is not a new invariant.

THE FIXTURE IS `D2`, the case that pays for the whole keyword channel: the
query asks about clipping in prose, the answer is a CONSTANT, and cosine buries
the constant because an identifier is not prose. Measured on the real corpus,
`CLIP_NORM = 1.5` sits at place 46 of 82 on codestral and place 4 on BM25.
"""

from __future__ import annotations

import math

import pytest

from labpilot.api import services
from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    search,
    write_artifact,
)

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
DIM = 3

QUERY_VECTOR = (1.0, 0.0, 0.0)


# Chunk `i` sits at angle `i * pi/40` from the query, so cosine falls smoothly
# from 1.0 at i=0 to 0.0 at i=20. Nothing here is a magic number: every score
# follows from an angle, so the expected order is arithmetic.
#
# THE ANSWER IS MID-PACK ON PURPOSE, and the first draft of this file got that
# wrong in a way worth keeping. It buried the answer at the very BOTTOM - one
# vector pointing the opposite way - and the test failed. The keyword channel
# was healthy the whole time (bm25 returned exactly chunk 20, score 6.39); the
# FIXTURE was impossible:
#
#     min-max puts the worst dense hit at 0.0 and the best at 1.0, and
#     alpha = 0.85 caps the keyword channel's whole contribution at 0.15.
#     So a chunk ranked LAST by cosine cannot be lifted past a chunk ranked
#     FIRST at ANY keyword score. 0.15 < 0.85, always.
#
# That is a real bound on what fusion can do, and it matches what was measured:
# `D2` sits at place 46 of 82 on cosine - mid-pack - not at place 82. The
# keyword channel rescues the middle, never the floor.
def _graded(index: int) -> tuple[float, float, float]:
    angle = index * math.pi / 40
    return (math.cos(angle), math.sin(angle), 0.0)


ANSWER_AT = 12

QUESTION = "how are gradients clipped to a global norm before the step"
ANSWER = "CLIP_NORM = 1.5"
FILLER = "the dataloader shuffles the training split each epoch"


@pytest.fixture
def corpus(db) -> str:
    """One chunk only BM25 can find, buried MID-PACK by cosine.

    The identifier appears in exactly one chunk of twenty-one, so its IDF is
    high - which is the whole reason BM25 beats `ts_rank` here and why this
    fixture cannot be shrunk to two chunks. `ts_rank` is handed ONE document
    and cannot know document frequency at all.
    """
    artifact_id = "B-fusion"
    write_artifact(
        db,
        ArtifactRecord(
            id=artifact_id, name="train.py", side="B", embedding_model=MODEL, dim=DIM
        ),
        [
            ChunkRecord(
                chunk_index=index,
                text=ANSWER if index == ANSWER_AT else f"{FILLER} number {index}",
                header=f"[train.py - part {index}]",
                source="train.py",
                start_line=index * 10,
                end_line=index * 10 + 5,
                vector=_graded(index),
            )
            for index in range(21)
        ],
    )
    return artifact_id


def places(hits) -> dict[int, int]:
    return {hit.chunk_index: place for place, hit in enumerate(hits)}


def test_the_keyword_channel_lifts_what_cosine_buried(db, corpus):
    """The end-to-end claim, and both halves are asserted.

    A test that only checked the final order could pass while the fusion did
    nothing, so the PREMISE is asserted first: cosine really does bury the
    answer. Without that line this becomes "the answer ranks well", which is
    true of a corpus where it always ranked well.
    """
    dense = search(db, corpus, QUERY_VECTOR, model=MODEL, limit=50)

    assert places(dense)[ANSWER_AT] == ANSWER_AT, (
        "premise: cosine must bury the constant mid-pack, or there is nothing "
        "for the keyword channel to rescue and this test proves nothing"
    )

    fused = services._fused(db, corpus, QUESTION, dense)

    assert places(fused)[ANSWER_AT] < places(dense)[ANSWER_AT], (
        "the keyword channel returned nothing, or the fusion discarded it - "
        "either way every answer is vector-alone and the slice 8 v3 decision "
        "is not in effect"
    )


def test_a_question_matching_no_lexeme_still_answers_on_vector_alone(db, corpus):
    """The degrade path, on real rows rather than a stub.

    A keyword channel that finds nothing must be invisible, not fatal. This is
    the same shape as `skip()` when no reranker is available: the vector
    channel is worth the whole answer, the keyword channel is worth +8.7
    queries out of 423, and the small one must never take the large one down.
    """
    dense = search(db, corpus, QUERY_VECTOR, model=MODEL, limit=50)

    fused = services._fused(db, corpus, "zzzqqq unrelatedgibberish", dense)

    assert [hit.chunk_index for hit in fused] == [hit.chunk_index for hit in dense]
