import time

import pytest
from dotenv import load_dotenv

from labpilot.llm import CHAIN
from tests.smoke.live import call_live, tier_case

load_dotenv()

REASONING_FLOOR = 8192

# A pool that allows only a few requests a minute cannot be walked back to back.
# Routeway allows 5 a minute in ONE pool and this file calls its seven tiers
# almost in a row - the six Gemma variants are adjacent - so the last ones came
# back 429 "Account per-minute rate limit exceeded (5 RPM)" on the first live
# run. That is our test outrunning a published limit, not a dead tier. 13s
# between calls keeps it under 5 a minute.
SECONDS_BETWEEN_CALLS = {"ROUTEWAY_API_KEY": 13.0}

_last_call: dict[str, float] = {}


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

    def once():
        # Paced on EVERY attempt, so a retry cannot outrun the limit either.
        _wait_for_turn(provider)
        return provider.complete(prompt, max_tokens=budget)

    return call_live(once, name=provider.name)


@pytest.mark.smoke
@pytest.mark.parametrize("provider", [tier_case(p) for p in CHAIN])
def test_every_tier_answers_a_real_prompt(provider):
    budget = min(
        REASONING_FLOOR, provider.max_output_tokens, provider.context_window // 2
    )
    result = _complete(provider, budget)

    assert result.text
    assert result.tier == provider.tier
    assert result.model
