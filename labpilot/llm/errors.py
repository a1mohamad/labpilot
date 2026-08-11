from __future__ import annotations

from labpilot.llm.contracts import Attempt


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: str | None = None,
        retry_after: int | None = None,
        reset_at: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.reset_at = reset_at


class AllFreeTiersExhausted(Exception):
    def __init__(self, attempts: tuple[Attempt, ...]) -> None:
        super().__init__(
            "All free tiers failed: "
            + "; ".join(f"Tier {a.tier} {a.model}: {a.error}" for a in attempts)
        )
        self.attempts = attempts
