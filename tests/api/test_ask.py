"""The two number spaces, and the cut that depends on which path ran.

No database and no network: these pin the pure decisions inside the ask path,
which are the ones that fail SILENTLY rather than loudly.
"""

from __future__ import annotations

from labpilot.api import services
from labpilot.rerank import SKIP, Ranking
from labpilot.store import SearchHit

FIRST_ID = 100


def hit(index: int, score: float = 0.5) -> SearchHit:
    """Chunk ids start at 100, never at 0.

    Slice 5 learned this: a fixture numbered from zero cannot tell a chunk_index
    from a list position, because both are small integers. Offsetting makes the
    confusion provable instead of plausible.
    """
    return SearchHit(
        chunk_index=FIRST_ID + index,
        text=f"chunk {FIRST_ID + index}",
        header=f"[train.py - part {index}]",
        source="train.py",
        start_line=index * 10,
        end_line=index * 10 + 5,
        score=score,
    )


def test_a_reranked_position_is_read_as_a_position_and_never_as_an_id():
    """THE TRAP THIS WHOLE STEP IS BUILT AROUND.

        SearchHit.chunk_index   an ID in the corpus
        Ranking.order           POSITIONS into the list we just passed

    They are both small integers and they mean different things. `hits[p]` is
    right; treating `p` as an id cites the wrong file and line with complete
    confidence, and nothing raises.
    """
    hits = tuple(hit(i) for i in range(3))
    reversed_order = Ranking(order=(2, 1, 0), model="fake-rerank")

    best = services._best("q", hits, rank=lambda *_, **__: reversed_order)

    assert [h.chunk_index for h in best] == [102, 101, 100]


def test_a_skipped_rerank_keeps_the_VECTOR_number_not_the_reranked_one():
    """skip() truncates to whatever top_n it is handed, so we must not hand it one.

    If every tier fails, the chain returns the retrieval order unchanged - and
    cutting that to RERANK_TOP_N would apply a number calibrated for a path
    that did not run. Ranking carries model=SKIP, so the cut is made on the
    visible fact rather than on a guess.
    """
    hits = tuple(hit(i) for i in range(40))
    declined = Ranking(order=tuple(range(40)), model=SKIP)

    best = services._best("q", hits, rank=lambda *_, **__: declined)

    assert len(best) == services.VECTOR_TOP_N


def test_a_real_reranker_cuts_to_the_reranked_number():
    """The other half: when a tier DID order them, the tighter cut is earned."""
    hits = tuple(hit(i) for i in range(40))
    ordered = Ranking(order=tuple(range(40)), model="rerank-3-lite")

    best = services._best("q", hits, rank=lambda *_, **__: ordered)

    assert len(best) < services.VECTOR_TOP_N


def test_nothing_found_is_not_an_error():
    """An empty result is an answer. Reranking nothing would be a ValueError."""
    assert services._best("q", ()) == []
