from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from labpilot.rerank.contracts import SKIP, Ranking
from labpilot.rerank.errors import RerankError
from labpilot.rerank.registry import RERANK_CHAIN

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    name: str
    model: str

    def rank(
        self, query: str, documents: Sequence[str], *, top_n: int | None = ...
    ) -> Ranking: ...


def skip(documents: Sequence[str], *, top_n: int | None = None) -> Ranking:
    """Keep the order retrieval already produced, and say so.

    This is the last tier of the chain, and it is the reason the chain has no
    `AllRerankersExhausted`. Reranking re-orders a list that is already in a
    defensible order, so losing it costs quality and nothing else - where
    losing generation costs the answer itself. CLAUDE.md fixed that asymmetry
    long before any of this was built: "the one stage whose total failure is
    degraded, not fatal, so it is the correct thing to drop first".

    The result still carries `model=SKIP`, so the degradation is visible to
    whoever reads it rather than hidden. `Ranking.skipped` is what the API
    will render as a warning in slice 7, the same way MAX_TOKENS is rendered -
    a truncated report otherwise looks complete.
    """
    _check(documents, top_n)
    order = tuple(range(len(documents)))
    return Ranking(order=order if top_n is None else order[:top_n], model=SKIP)


def rerank(
    query: str,
    documents: Sequence[str],
    *,
    chain: Sequence[Reranker] = RERANK_CHAIN,
    top_n: int | None = None,
) -> Ranking:
    """Walk the chain, and end in skip rather than in an exception.

    A caller's bug and a provider's failure stay different exceptions, which
    is the oldest rule in this project: a blank query is a `ValueError` and
    must crash, because falling through three tiers to `skip` would report a
    typo as a degraded ranking and nobody would ever learn.
    """
    _check(documents, top_n)
    if not query.strip():
        raise ValueError("the rerank query must not be blank")

    for reranker in chain:
        try:
            return reranker.rank(query, documents, top_n=top_n)
        except RerankError as exc:
            logger.warning("%s failed, trying the next tier: %s", reranker.name, exc)

    logger.warning(
        "every reranker failed; keeping the retrieval order for %d documents",
        len(documents),
    )
    return skip(documents, top_n=top_n)


def _check(documents: Sequence[str], top_n: int | None) -> None:
    if not documents:
        raise ValueError("there are no documents to rank")
    if top_n is not None and top_n < 1:
        raise ValueError(f"top_n must be positive, got {top_n}")
