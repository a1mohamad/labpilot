from __future__ import annotations

from dataclasses import dataclass

# The name the chain reports when every tier failed and nothing reordered
# anything. It is a real outcome, not an error: reranking is the one stage in
# this pipeline whose total failure is DEGRADED rather than fatal, so the
# chain always returns a Ranking and never raises an "exhausted" signal the
# way LLMClient must.
SKIP = "skip"


@dataclass(frozen=True, slots=True, kw_only=True)
class Ranking:
    """One reordering of the documents that were sent.

    `order` holds POSITIONS into the documents the caller passed, best first -
    never chunk ids, never rows. rerank/ is an adapter and may not import
    store/, so it cannot see a SearchHit; the caller owns the translation back
    to real chunks. That constraint gives the right shape anyway, because a
    cross-encoder genuinely knows nothing except "here are some strings".

    `order` may be SHORTER than the documents sent: every provider accepts a
    top-n and returns only the survivors. It may never be longer, may never
    name a document that was not sent, and may never name one twice - each of
    those would silently put the wrong chunk in front of the model.

    `scores` is empty when the producer scored nothing, which is exactly what
    SKIP is: an order with no judgement behind it.
    """

    order: tuple[int, ...]
    scores: tuple[float, ...] = ()
    model: str = SKIP

    def __post_init__(self) -> None:
        if len(set(self.order)) != len(self.order):
            raise ValueError(
                f"{self.model}: a document appears twice in the order "
                f"{self.order}, so one chunk would reach the model twice"
            )
        if any(position < 0 for position in self.order):
            raise ValueError(f"{self.model}: negative position in {self.order}")
        if self.scores and len(self.scores) != len(self.order):
            raise ValueError(
                f"{self.model}: {len(self.order)} ranked position(s) but "
                f"{len(self.scores)} score(s): they must align or be absent"
            )

    @property
    def skipped(self) -> bool:
        return self.model == SKIP
