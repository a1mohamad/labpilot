import time

import pytest
from dotenv import load_dotenv

from labpilot.llm import CHAIN, LLMError
from labpilot.llm.defaults import RETRYABLE_STATUSES

load_dotenv()

REASONING_FLOOR = 8192
KNOWN_DEAD = {"GLM-5.2"}

# A pool that allows only a few requests a minute cannot be walked back to back.
# Routeway allows 5 a minute in ONE pool and this file calls its seven tiers
# almost in a row - the six Gemma variants are adjacent - so the last ones came
# back 429 "Account per-minute rate limit exceeded (5 RPM)" on the first live
# run. That is our test outrunning a published limit, not a dead tier. 13s
# between calls keeps it under 5 a minute.
SECONDS_BETWEEN_CALLS = {"ROUTEWAY_API_KEY": 13.0}

# Routeway is also TRANSIENT in three more ways, all seen on 2026-09-29 and
# each gone on the next call: a 429 "model_overloaded" for one congested model
# (its own message says to retry), a 502 Cloudflare error page, and a request
# that never returns - through the VPN's proxy the tunnel setup alone can pass
# the 10s connect timeout and surfaces as "Read timed out (read timeout=10.0)".
# The chain retries a 429 twice, so the smoke test retries these for the pools
# it paces and reports a tier as dead only when it stays down.
RETRIES_FOR_PACED_POOLS = 2
WAIT_BEFORE_RETRY = 20.0
BAD_GATEWAY = 502


def _is_transient(error: LLMError) -> bool:
    """No status at all means the request never got an answer - a transport
    failure, not a verdict from the provider."""
    return (
        error.status is None
        or error.status in RETRYABLE_STATUSES
        or error.status == BAD_GATEWAY
    )


_last_call: dict[str, float] = {}


def _case(provider):
    marks = (
        [pytest.mark.xfail(reason="no free allocation on this account", strict=False)]
        if provider.name in KNOWN_DEAD
        else []
    )
    return pytest.param(provider, marks=marks, id=provider.name)


def _wait_for_turn(provider) -> None:
    gap = SECONDS_BETWEEN_CALLS.get(provider.api_key_env)
    if gap is None:
        return
    last = _last_call.get(provider.pool)
    if last is not None:
        time.sleep(max(0.0, gap - (time.monotonic() - last)))
    _last_call[provider.pool] = time.monotonic()


def _complete(provider, budget: int):
    prompt = "Reply with one short sentence: you are online."
    retries = (
        RETRIES_FOR_PACED_POOLS if provider.api_key_env in SECONDS_BETWEEN_CALLS else 0
    )
    for attempt in range(retries + 1):
        _wait_for_turn(provider)
        try:
            return provider.complete(prompt, max_tokens=budget)
        except LLMError as exc:
            if not _is_transient(exc) or attempt == retries:
                raise
            time.sleep(WAIT_BEFORE_RETRY)


@pytest.mark.smoke
@pytest.mark.parametrize("provider", [_case(p) for p in CHAIN])
def test_every_tier_answers_a_real_prompt(provider):
    budget = min(
        REASONING_FLOOR, provider.max_output_tokens, provider.context_window // 2
    )
    result = _complete(provider, budget)

    assert result.text
    assert result.tier == provider.tier
    assert result.model
