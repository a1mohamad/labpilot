from __future__ import annotations

from labpilot.llm.contracts import Attempt


class LLMError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
        reset_at: float | None = None,
        rate_limit: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.reset_at = reset_at
        self.rate_limit = rate_limit


class AllFreeTiersExhausted(Exception):
    def __init__(self, attempts: tuple[Attempt, ...]) -> None:
        super().__init__(
            "All free tiers failed: "
            + "; ".join(f"Tier {a.tier} {a.model}: {a.error}" for a in attempts)
        )
        self.attempts = attempts
