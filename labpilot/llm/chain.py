from __future__ import annotations

import contextvars
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from labpilot.llm._pacing import enter, leave
from labpilot.llm._rooms import book, with_margin
from labpilot.llm.contracts import Attempt, LLMResult, Tool
from labpilot.llm.defaults import (
    DEFAULT_CALL_STOP,
    DEFAULT_MAX_REJECTED_ANSWERS,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TOTAL_BUDGET,
    HTTP_TOO_MANY_REQUESTS,
    RATE_LIMIT_WINDOW,
    RETRY_DELAYS,
    RETRYABLE_STATUSES,
    TURN_WAIT_MAX,
)
from labpilot.llm.errors import AllFreeTiersExhausted, LLMError
from labpilot.llm.registry import CHAIN
from labpilot.timing import log_call
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)


class Provider(Protocol):
    name: str
    tier: int
    api_key_env: str

    @property
    def pool(self) -> str: ...

    def complete(
        self, prompt: str, *, max_tokens: int = ..., tool: Tool | None = ...
    ) -> LLMResult: ...


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


def worth_a_second_try(error: LLMError) -> bool:
    """Can asking the SAME tier again change the answer? (RETRY_DELAYS)

    Yes for no answer at all (status None: a reset connection, an empty reply)
    and for the busy or failing statuses. No for a refusal that cannot change, a
    daily 429, a tier that is not on this plan, and anything the chain marked
    `retryable=False` (refused locally, a hang that was cut off).
    """
    if error.retryable is False:
        return False
    if pool_is_exhausted(error) or model_is_unavailable(error):
        return False
    return error.status is None or error.status in RETRYABLE_STATUSES


def wait_before_retry(
    error: LLMError, attempt: int, delays: tuple[float, ...] = RETRY_DELAYS
) -> float | None:
    """Seconds to wait before retry number `attempt` (0 or 1), or None to give up.

    The wait is the fixed 1 s or 3 s. A provider that says "come back in 30 s"
    is not waited for: the walk goes to the next tier instead.
    """
    if attempt >= len(delays):
        return None
    fixed = delays[attempt]
    asked = error.retry_after
    if asked is None and error.reset_at is not None:
        asked = max(0.0, error.reset_at - time.time())
    if asked is not None and asked > delays[-1]:
        return None
    return max(fixed, asked or 0.0)


def _call_with_stop(call: Callable[[], LLMResult], stop: float | None) -> LLMResult:
    """Run `call`, and give up on it after `stop` seconds (None = never).

    The call keeps running in its thread until it ends by itself, because a
    blocked HTTP call cannot be killed; its answer is thrown away. The context is
    copied so that the timing of the step still finds its name.
    """
    if stop is None:
        return call()

    box: dict[str, object] = {}
    context = contextvars.copy_context()

    def run() -> None:
        try:
            box["result"] = context.run(call)
        except BaseException as exc:  # carried to the caller below
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(stop)
    if worker.is_alive():
        raise LLMError(f"no answer after {stop:.0f}s", retryable=False)
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["result"]  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMClient:
    chain: tuple[Provider, ...] = CHAIN
    total_budget: float = DEFAULT_TOTAL_BUDGET
    max_rejected_answers: int = DEFAULT_MAX_REJECTED_ANSWERS
    # A call that has not answered after this long is given up (None = never).
    call_stop: float | None = DEFAULT_CALL_STOP
    # The waits before the 1st and the 2nd retry of one tier. () = no retry, which
    # a measurement of one model alone wants. The product never changes it.
    retry_delays: tuple[float, ...] = RETRY_DELAYS

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool: Tool | None = None,
        problem_with: Callable[[LLMResult], str | None] | None = None,
    ) -> LLMResult:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")

        started = time.monotonic()
        deadline = started + self.total_budget
        attempts: list[Attempt] = []
        dead_pools: set[str] = set()
        rejected = 0
        tokens = with_margin(estimate_tokens(prompt))

        # ONE walk along the chain, and it never waits for a tier. A tier is
        # skipped at once when its pool is spent, its minute room is full (D70:
        # the next tier is often the same model on another key, with space),
        # another call is open on an account that takes one at a time, or the
        # account must rest longer than TURN_WAIT_MAX. A tier that is called and
        # does not answer is asked again after 1 s and after 3 s, then the walk
        # goes on.
        for provider in self.chain:
            pool = provider.pool

            if pool in dead_pools:
                attempts.append(self._attempt(provider, f"skipped: {pool} exhausted"))
                continue

            if time.monotonic() >= deadline:
                attempts.append(self._attempt(provider, "skipped: time budget spent"))
                continue

            wait = book(
                pool,
                tokens=tokens,
                token_limit=getattr(provider, "max_input_tokens", None),
                request_limit=getattr(provider, "requests_per_minute", None),
            )
            if wait > 0:
                attempts.append(
                    self._attempt(provider, f"skipped: room full for {wait:.0f}s")
                )
                continue

            account = provider.api_key_env
            concurrent = getattr(provider, "max_concurrent", None)
            reason, rest = enter(
                account,
                concurrent=concurrent,
                gap=getattr(provider, "seconds_between_calls", 0.0),
                max_wait=TURN_WAIT_MAX,
            )
            if reason is not None:
                attempts.append(self._attempt(provider, f"skipped: {reason}"))
                continue
            if rest > 0:
                time.sleep(rest)

            try:
                result = self._complete_with_retries(
                    provider,
                    prompt,
                    max_tokens=max_tokens,
                    tool=tool,
                    deadline=deadline,
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
            finally:
                leave(
                    account,
                    concurrent=concurrent,
                    quiet=getattr(provider, "seconds_after_call", 0.0),
                )

            problem = problem_with(result) if problem_with is not None else None
            if problem is None:
                log_call(
                    tool=tool.name if tool else "",
                    seconds=time.monotonic() - started,
                    tier=result.tier,
                    model=result.model,
                    failed=len(attempts),
                )
                return replace(result, attempts=tuple(attempts))

            # The tier answered, but the caller says the answer is wrong. The next
            # tier may do better, so the walk goes on. The pool is NOT marked dead
            # (the quota is fine) and the same tier is NOT asked again (at
            # temperature 0 it would say the same thing).
            logger.warning("tier %d: answer rejected: %s", provider.tier, problem)
            attempts.append(self._attempt(provider, f"answer rejected: {problem}"))
            rejected += 1
            if rejected >= self.max_rejected_answers:
                break

        log_call(
            tool=tool.name if tool else "",
            seconds=time.monotonic() - started,
            tier=None,
            model=None,
            failed=len(attempts),
        )
        raise AllFreeTiersExhausted(tuple(attempts))

    def _complete_with_retries(
        self,
        provider: Provider,
        prompt: str,
        *,
        max_tokens: int,
        tool: Tool | None,
        deadline: float,
    ) -> LLMResult:
        attempt = 0
        while True:
            try:
                return _call_with_stop(
                    lambda: provider.complete(prompt, max_tokens=max_tokens, tool=tool),
                    self.call_stop,
                )
            except LLMError as exc:
                if not worth_a_second_try(exc):
                    raise

                delay = wait_before_retry(exc, attempt, self.retry_delays)
                if delay is None or time.monotonic() + delay >= deadline:
                    raise

                logger.warning(
                    "tier %d did not answer, trying again in %.0fs (retry %d)",
                    provider.tier,
                    delay,
                    attempt + 1,
                )
                time.sleep(delay)
                attempt += 1

    def _attempt(self, provider: Provider, error: str) -> Attempt:
        return Attempt(tier=provider.tier, model=provider.name, error=error)
