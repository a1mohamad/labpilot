from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import Protocol

from labpilot.llm.contracts import Attempt, LLMResult
from labpilot.llm.defaults import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_DELAY,
    DEFAULT_MAX_RETRIES_PER_TIER,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOTAL_BUDGET,
    HTTP_TOO_MANY_REQUESTS,
    RATE_LIMIT_WINDOW,
    RETRYABLE_STATUSES,
)
from labpilot.llm.errors import AllFreeTiersExhausted, LLMError
from labpilot.llm.registry import CHAIN

logger = logging.getLogger(__name__)


class Provider(Protocol):
    name: str
    tier: int
    api_key_env: str

    @property
    def pool(self) -> str: ...

    def complete(self, prompt: str, *, max_tokens: int = ...) -> LLMResult: ...


def delay_for(error: LLMError, attempt: int, *, base: float) -> float:
    if error.retry_after is not None:
        return error.retry_after
    if error.reset_at is not None:
        return max(0.0, error.reset_at - time.time())

    return base * 2**attempt


def pool_is_exhausted(error: LLMError) -> bool:
    if error.status != HTTP_TOO_MANY_REQUESTS:
        return False
    if error.retry_after is not None:
        return error.retry_after > RATE_LIMIT_WINDOW
    if error.reset_at is not None:
        return error.reset_at - time.time() > RATE_LIMIT_WINDOW
    return False


def model_is_unavailable(error: LLMError) -> bool:
    if error.status != HTTP_TOO_MANY_REQUESTS:
        return False

    return error.rate_limit == 0


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMClient:
    chain: tuple[Provider, ...] = CHAIN
    max_retries_per_tier: int = DEFAULT_MAX_RETRIES_PER_TIER
    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY
    total_budget: float = DEFAULT_TOTAL_BUDGET

    def generate(
        self, prompt: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> LLMResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        deadline = time.monotonic() + self.total_budget
        attempts: list[Attempt] = []
        dead_pools: set[str] = set()

        for provider in self.chain:
            pool = provider.pool

            if pool in dead_pools:
                attempts.append(self._attempt(provider, f"skipped: {pool} exhausted"))
                continue

            if time.monotonic() >= deadline:
                attempts.append(self._attempt(provider, "skipped: time budget spent"))
                continue

            try:
                result = self._complete_with_retries(
                    provider, prompt, max_tokens=max_tokens, deadline=deadline
                )
            except LLMError as exc:
                if model_is_unavailable(exc):
                    attempts.append(
                        self._attempt(provider, f"not available on this account: {exc}")
                    )
                    continue

                if exc.status == HTTP_TOO_MANY_REQUESTS:
                    dead_pools.add(pool)
                attempts.append(self._attempt(provider, str(exc)))
                continue

            return replace(result, attempts=tuple(attempts))

        raise AllFreeTiersExhausted(tuple(attempts))

    def _complete_with_retries(
        self, provider: Provider, prompt: str, *, max_tokens: int, deadline: float
    ) -> LLMResult:
        attempt = 0
        while True:
            try:
                return provider.complete(prompt, max_tokens=max_tokens)
            except LLMError as exc:
                if exc.status not in RETRYABLE_STATUSES:
                    raise
                if (
                    pool_is_exhausted(exc)
                    or model_is_unavailable(exc)
                    or attempt >= self.max_retries_per_tier
                ):
                    raise

                delay = delay_for(exc, attempt, base=self.base_delay)
                if delay > self.max_delay or time.monotonic() + delay >= deadline:
                    raise

                logger.warning(
                    "tier %d rate limited, waiting %.1fs before retry %d",
                    provider.tier,
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)
                attempt += 1

    def _attempt(self, provider: Provider, error: str) -> Attempt:
        return Attempt(tier=provider.tier, model=provider.name, error=error)
