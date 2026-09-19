"""The keyword channel is WIRED, not merely built.

Slice 5 built `bm25_search` and `weighted_rrf` and gave them no caller. Slice 8
v1 then recorded "the keyword channel is switched ON ... it now has a caller",
and that sentence was false for three sessions: grepping labpilot/ for
`bm25_search` found the re-export in store/__init__.py and nothing else.

It is the same defect slice 7 hit with the rerank chain - BUILT BUT NEVER
BOUND - and it is invisible from the outside, because a vector-only answer
looks exactly like a fused one. So the test that matters is not "does fusion
compute the right order" but "does the ask path CALL it at all".
"""

from __future__ import annotations

import pytest

from labpilot.api import services
from labpilot.store import ArtifactRecord, SearchHit, StoredArtifact, StoreError

FIRST_ID = 100


def hit(index: int, score: float) -> SearchHit:
    """Ids start at 100, so a position can never masquerade as an id."""
    return SearchHit(
        chunk_index=FIRST_ID + index,
        text=f"chunk {FIRST_ID + index}",
        header=f"[train.py - part {index}]",
        source="train.py",
        start_line=index * 10,
        end_line=index * 10 + 5,
        score=score,
    )


@pytest.fixture
def side_b():
    return {
        "B": StoredArtifact(
            artifact=ArtifactRecord(
                id="B-1", name="train.py", side="B", embedding_model="m", dim=3
            ),
            chunks=50,
            characters=5_000,
        )
    }


@pytest.fixture
def no_embed(monkeypatch):
    monkeypatch.setattr(services, "_embed_question", lambda *a, **k: (1.0, 0.0, 0.0))


def test_the_ask_path_really_calls_the_keyword_channel(monkeypatch, side_b, no_embed):
    """THE ONE THAT WOULD HAVE CAUGHT THREE SESSIONS OF THIS BEING OFF."""
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(services, "search", lambda *a, **k: (hit(0, 0.9),))
    monkeypatch.setattr(
        services,
        "bm25_search",
        lambda conn, artifact_id, question, **k: (
            asked.append((artifact_id, question)) or (hit(0, 3.0),)
        ),
    )

    services._retrieved(object(), side_b, question="where is the norm clipped?")

    assert asked == [("B-1", "where is the norm clipped?")]


def test_a_keyword_only_hit_can_enter_the_window(monkeypatch, side_b, no_embed):
    """The rescue, and the reason the channel exists at all.

    `D2` is the measured case: the constant CLIP_NORM = 1.5 sat at place 46 on
    cosine and place 4 on BM25. A chunk the vector channel never returned must
    be able to arrive - otherwise fusion can only reorder, and the whole
    +8.7-query gain is unreachable.
    """
    monkeypatch.setattr(services, "search", lambda *a, **k: (hit(0, 0.9),))
    monkeypatch.setattr(services, "bm25_search", lambda *a, **k: (hit(7, 9.0),))

    chunks = services._retrieved(object(), side_b, question="q")

    assert 107 in [c.chunk_index for c in chunks], (
        "a chunk found only by BM25 never reached the prompt, so fusion can "
        "reorder but cannot rescue"
    )


def test_a_broken_keyword_channel_degrades_to_vector_alone(
    monkeypatch, side_b, no_embed
):
    """DEGRADE, LOUDLY - never take the answer down with it.

    The keyword channel is worth +8.7 queries of 423 and costs 4-5 extra round
    trips, so it has more ways to fail than the vector channel and far less to
    lose. Same shape as skip() when no reranker is available.
    """
    monkeypatch.setattr(services, "search", lambda *a, **k: (hit(0, 0.9), hit(1, 0.8)))

    def broken(*_args, **_kwargs):
        raise StoreError("the tsvector column is missing")

    monkeypatch.setattr(services, "bm25_search", broken)

    chunks = services._retrieved(object(), side_b, question="q")

    assert [c.chunk_index for c in chunks] == [100, 101]


def test_the_fused_window_never_exceeds_what_search_returns(monkeypatch, side_b):
    """Two 50-hit channels union to as many as 100.

    RERANK_WINDOW and VECTOR_TOP_N are both calibrated against a 50-candidate
    window PER SIDE, so handing them 100 would silently change two measured
    numbers by changing what they are a fraction of.
    """
    dense = tuple(hit(i, 1.0 - i / 100) for i in range(services.SEARCH_LIMIT))
    sparse = tuple(hit(i, 1.0) for i in range(50, 50 + services.SEARCH_LIMIT))
    monkeypatch.setattr(services, "bm25_search", lambda *a, **k: sparse)

    fused = services._fused(object(), "B-1", "q", dense)

    assert len(fused) == services.SEARCH_LIMIT
