from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from labpilot.rerank import SKIP, Ranking, RerankError, rerank, skip

DOCS = ("first", "second", "third")


@dataclass
class FakeReranker:
    name: str
    model: str
    answer: Ranking | None = None
    error: Exception | None = None
    calls: list[tuple[str, tuple[str, ...], int | None]] = field(default_factory=list)

    def rank(
        self, query: str, documents: Sequence[str], *, top_n: int | None = None
    ) -> Ranking:
        self.calls.append((query, tuple(documents), top_n))
        if self.error is not None:
            raise self.error
        assert self.answer is not None
        return self.answer


def working(model: str, order=(2, 0, 1)) -> FakeReranker:
    return FakeReranker(
        name=model, model=model, answer=Ranking(order=order, model=model)
    )


def broken(model: str) -> FakeReranker:
    return FakeReranker(name=model, model=model, error=RerankError(f"{model} is down"))


def test_the_first_tier_that_answers_wins_and_the_rest_are_never_called():
    first, second = working("tier-1"), working("tier-2")

    ranking = rerank("why", DOCS, chain=(first, second))

    assert ranking.model == "tier-1"
    assert len(first.calls) == 1
    assert second.calls == []


def test_a_provider_failure_moves_to_the_next_tier():
    dead, alive = broken("tier-1"), working("tier-2")

    ranking = rerank("why", DOCS, chain=(dead, alive))

    assert ranking.model == "tier-2"
    assert len(alive.calls) == 1


def test_when_every_tier_fails_the_retrieval_order_survives_and_says_so():
    """Reranking is the one stage whose total failure is degraded, not fatal.

    So there is no AllRerankersExhausted to raise: the chain returns the order
    retrieval already produced, and marks it SKIP so the degradation is
    visible to whoever reads the result instead of hidden inside it.
    """
    ranking = rerank("why", DOCS, chain=(broken("tier-1"), broken("tier-2")))

    assert ranking.order == (0, 1, 2)
    assert ranking.model == SKIP
    assert ranking.skipped
    assert ranking.scores == ()


def test_a_blank_query_crashes_and_never_degrades_to_skip():
    """The oldest rule in this project, at a new layer: a caller's bug and a
    provider's failure are different exceptions.

    Falling through three tiers to `skip` would report a typo as a slightly
    worse ranking, and nobody would ever learn it happened.
    """
    tier = working("tier-1")

    with pytest.raises(ValueError, match="must not be blank"):
        rerank("   ", DOCS, chain=(tier,))

    assert tier.calls == []


def test_no_documents_crashes_rather_than_returning_an_empty_ranking():
    with pytest.raises(ValueError, match="no documents to rank"):
        rerank("why", [], chain=(working("tier-1"),))


def test_top_n_reaches_the_tier_that_serves_the_call():
    tier = working("tier-1", order=(2,))

    rerank("why", DOCS, chain=(tier,), top_n=1)

    assert tier.calls[0][2] == 1


def test_skip_keeps_retrieval_order_and_honours_top_n():
    assert skip(DOCS).order == (0, 1, 2)
    assert skip(DOCS, top_n=2).order == (0, 1)


def test_skip_refuses_a_caller_bug_like_every_other_tier():
    with pytest.raises(ValueError, match="no documents to rank"):
        skip([])

    with pytest.raises(ValueError, match="top_n must be positive"):
        skip(DOCS, top_n=0)
