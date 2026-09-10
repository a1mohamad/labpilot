from __future__ import annotations

import pytest

from labpilot.rerank.contracts import SKIP, Ranking


def test_a_ranking_keeps_the_order_it_was_given():
    ranking = Ranking(order=(2, 0, 1), scores=(0.9, 0.5, 0.1), model="test-rerank")

    assert ranking.order == (2, 0, 1)
    assert ranking.model == "test-rerank"
    assert not ranking.skipped


def test_the_same_document_may_never_be_ranked_twice():
    """Two positions pointing at one chunk put that chunk in the prompt twice,
    and push a real answer out of the top_n window to make room for it."""
    with pytest.raises(ValueError, match="appears twice"):
        Ranking(order=(0, 1, 1), model="test-rerank")


def test_a_negative_position_is_refused():
    with pytest.raises(ValueError, match="negative position"):
        Ranking(order=(0, -1), model="test-rerank")


def test_scores_must_either_align_with_the_order_or_be_absent():
    with pytest.raises(ValueError, match="must align or be absent"):
        Ranking(order=(0, 1, 2), scores=(0.9, 0.5), model="test-rerank")


def test_an_order_with_no_scores_is_legal_because_that_is_what_skip_is():
    ranking = Ranking(order=(0, 1, 2))

    assert ranking.scores == ()
    assert ranking.model == SKIP
    assert ranking.skipped
