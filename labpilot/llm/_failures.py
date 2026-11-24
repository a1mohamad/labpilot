"""What a failed call means: ask the same tier again, or rest it."""

from __future__ import annotations

import time

from labpilot.llm import _health
from labpilot.llm.defaults import (
    HTTP_SERVICE_UNAVAILABLE,
    HTTP_TOO_MANY_REQUESTS,
    RATE_LIMIT_WINDOW,
    RETRY_DELAYS,
    RETRY_WAIT_MAX,
    RETRYABLE_STATUSES,
)
from labpilot.llm.errors import LLMError


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
    """Seconds to wait before retry number `attempt` (0 = first), or None to give up.

    A provider that says "come back in 30 s" is not waited for: the walk goes to
    the next tier instead.
    """
    if attempt >= len(delays):
        return None
    asked = error.retry_after
    if asked is None and error.reset_at is not None:
        asked = max(0.0, error.reset_at - time.time())
    if asked is not None and asked > RETRY_WAIT_MAX:
        return None
    return max(delays[attempt], asked or 0.0)


def note_failure(name: str, pool: str, error: LLMError) -> None:
    """Remember a failed call, so the next calls skip the tier (see _health.py)."""
    if error.status == HTTP_TOO_MANY_REQUESTS and not model_is_unavailable(error):
        asked = error.retry_after
        if asked is None and error.reset_at is not None:
            asked = max(0.0, error.reset_at - time.time())
        _health.rest(pool, _health.QUOTA, asked)
    elif error.status in (401, 402, 404) or model_is_unavailable(error):
        _health.rest(name, _health.GONE)
    elif error.status == HTTP_SERVICE_UNAVAILABLE:
        _health.rest(name, _health.OVERLOADED)
    elif error.slow:
        _health.rest(name, _health.SLOW)
    elif error.status is not None or error.retryable is not False:
        # Not a refusal of our own (too long, no key) and not an answer that
        # could not be read: those say nothing about the next call.
        _health.rest(name, _health.FAILED)
