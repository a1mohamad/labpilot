"""What a weekly smoke test does when a live call goes wrong.

FOUND 2026-09-29, reading four red Mondays in a row. About half of the 41
failures in the last run were not a dead provider, and the run could not tell
the difference:

    "high demand ... usually temporary"   Google 503 on about nine tiers. The
                                          chain retries a 503; the test did not
    "Rate limit exceeded"                 Mistral 429 on three tiers, every week
                                          for a month: a spent monthly quota
    "Connection reset by peer"            one call, gone on the next

A run that is always red is not an alarm. So this decides, in ONE place, what
each kind of failure means, and every live test goes through it:

    transient   wait and try again, the way the chain does
    spent quota XFAIL with the provider's own words, shown by -rxX. Not a
                failure: the tier is fine and the account is empty
    the rest    a real failure at once - a 403, a 404, a 400, a missing key.
                Retrying a missing key would only spend 30 seconds hiding it,
                and it is exactly what the missing Voyage secret looked like

Routeway is the sharpest example of "transient", all seen 2026-09-29 and each
gone on the next call: a 429 "model_overloaded" for one congested model, a 502
Cloudflare error page, and a request that never returns - through a VPN's proxy
the tunnel setup alone can pass the 10s connect timeout.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import pytest
import requests

from labpilot.embed import EmbeddingError
from labpilot.llm import KNOWN_DEAD, LLMError
from labpilot.llm.chain import pool_is_exhausted
from labpilot.llm.defaults import RETRYABLE_STATUSES
from labpilot.rerank import RerankError

T = TypeVar("T")

BAD_GATEWAY = 502
TOO_MANY_REQUESTS = 429

# Seconds to wait before retry 1 and retry 2. The chain waits 1s and 2s, which
# is right for a server it can afford to ask again at once; a smoke run has
# nothing to hurry for, and Google's own message says demand spikes are
# "usually temporary".
WAITS = (10.0, 20.0)

PROVIDER_ERRORS = (LLMError, EmbeddingError, RerankError)


def tier_case(provider):
    """A parametrized case for one generator tier, xfailed when it is known dead.

    The list is the REGISTRY's, never a copy: this file used to keep its own
    `{"GLM-5.2"}` while the registry named four, so three dead routes failed
    every Monday. strict=False, so the day a route comes back it reports XPASS.
    """
    marks = (
        [
            pytest.mark.xfail(
                reason="a known dead route - see KNOWN_DEAD in llm/registry.py",
                strict=False,
            )
        ]
        if provider.name in KNOWN_DEAD
        else []
    )
    return pytest.param(provider, marks=marks, id=provider.name)


def _causes(exc: BaseException):
    """The error and everything it was raised from, outermost first."""
    while exc is not None:
        yield exc
        exc = exc.__cause__


def _llm_error(exc: BaseException) -> LLMError | None:
    """A reranker wraps the LLM layer's error, so look through the chain."""
    return next((e for e in _causes(exc) if isinstance(e, LLMError)), None)


def _is_transient(exc: BaseException) -> bool:
    status = getattr(exc, "status", None)
    if status is not None:
        return status in RETRYABLE_STATUSES or status == BAD_GATEWAY
    # No status: transient only if a real network fault sits underneath. A
    # missing key raises with no status AND no network cause, and must fail.
    return any(
        isinstance(e, requests.exceptions.RequestException) for e in _causes(exc)
    )


def _quota_is_spent(exc: BaseException) -> bool:
    error = _llm_error(exc)
    return error is not None and pool_is_exhausted(error)


def _wait_before(attempt: int, exc: BaseException) -> float:
    error = _llm_error(exc)
    hinted = 0.0 if error is None or error.retry_after is None else error.retry_after
    return max(WAITS[attempt], hinted)


def call_live(call: Callable[[], T], *, name: str) -> T:
    """Run one live call, retrying only what the chain itself would retry."""
    tries = len(WAITS) + 1
    for attempt in range(tries):
        try:
            return call()
        except PROVIDER_ERRORS as exc:
            if _quota_is_spent(exc):
                pytest.xfail(f"{name}: quota is spent - {str(exc)[:200]}")
            if not _is_transient(exc):
                raise
            if attempt == tries - 1:
                if getattr(exc, "status", None) == TOO_MANY_REQUESTS:
                    pytest.xfail(
                        f"{name}: still rate limited after {tries} tries - "
                        f"{str(exc)[:200]}"
                    )
                raise
            time.sleep(_wait_before(attempt, exc))
