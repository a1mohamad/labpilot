from __future__ import annotations

import time

import pytest

from labpilot.llm.chain import LLMClient, delay_for, pool_is_exhausted
from labpilot.llm.contracts import LLMResult
from labpilot.llm.errors import AllFreeTiersExhausted, LLMError


class FakeProvider:
    def __init__(self, *, name, tier, api_key_env, outcomes):
        self.name = name
        self.tier = tier
        self.api_key_env = api_key_env
        self.outcomes = list(outcomes)
        self.calls = 0

    def complete(self, prompt, *, max_tokens=1024):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(text=outcome, model=self.name, tier=self.tier)


def ok(name, tier, *, key="KEY_A"):
    return FakeProvider(name=name, tier=tier, api_key_env=key, outcomes=["answer"])


def fails(name, tier, error, *, key="KEY_A"):
    return FakeProvider(name=name, tier=tier, api_key_env=key, outcomes=[error])


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", slept.append)
    return slept


def test_first_tier_answers_without_touching_the_rest():
    second = ok("Second", 2)
    result = LLMClient(chain=(ok("First", 1), second)).generate("hello")

    assert result.tier == 1
    assert result.attempts == ()
    assert second.calls == 0


def test_falls_through_to_the_next_tier_when_one_fails():
    client = LLMClient(
        chain=(
            fails("First", 1, LLMError("First: HTTP 500")),
            ok("Second", 2, key="KEY_B"),
        )
    )
    result = client.generate("hello")

    assert result.tier == 2
    assert [a.tier for a in result.attempts] == [1]


def test_retries_the_same_tier_once_when_rate_limited(no_sleep):
    first = FakeProvider(
        name="First",
        tier=1,
        api_key_env="KEY_A",
        outcomes=[LLMError("busy", status=429, retry_after=2.0), "answer"],
    )
    result = LLMClient(chain=(first,)).generate("hello")

    assert result.tier == 1
    assert first.calls == 2
    assert no_sleep == [2.0]


def test_does_not_wait_when_the_limit_resets_far_away(no_sleep):
    daily = LLMError("daily cap", status=429, reset_at=time.time() + 3600)
    first = fails("First", 1, daily)
    client = LLMClient(chain=(first, ok("Second", 2, key="KEY_B")))
    result = client.generate("hello")

    assert result.tier == 2
    assert first.calls == 1
    assert no_sleep == []


def test_skips_every_tier_sharing_an_exhausted_pool(no_sleep):
    daily = LLMError("daily cap", status=429, reset_at=time.time() + 3600)
    third = ok("Third", 3, key="POOL")
    client = LLMClient(
        chain=(
            fails("First", 1, daily, key="POOL"),
            fails("Second", 2, LLMError("boom"), key="OTHER"),
            third,
            ok("Fourth", 4, key="LAST"),
        )
    )
    result = client.generate("hello")

    assert result.tier == 4
    assert third.calls == 0
    assert "exhausted" in result.attempts[2].error


def test_raises_all_free_tiers_exhausted_carrying_every_attempt():
    client = LLMClient(
        chain=(
            fails("First", 1, LLMError("a")),
            fails("Second", 2, LLMError("b"), key="KEY_B"),
        )
    )
    with pytest.raises(AllFreeTiersExhausted) as caught:
        client.generate("hello")

    assert [a.tier for a in caught.value.attempts] == [1, 2]


def test_empty_prompt_raises_value_error():
    first = ok("First", 1)
    with pytest.raises(ValueError):
        LLMClient(chain=(first,)).generate("   ")

    assert first.calls == 0


def test_delay_prefers_the_servers_retry_after():
    error = LLMError("busy", status=429, retry_after=7.0, reset_at=time.time() + 900)
    assert delay_for(error, 0, base=1.0) == 7.0


def test_delay_falls_back_to_exponential_backoff():
    error = LLMError("busy", status=429)
    assert [delay_for(error, k, base=1.0) for k in range(4)] == [1.0, 2.0, 4.0, 8.0]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LLMError("server error", status=500), False),
        (LLMError("per minute", status=429, retry_after=5.0), False),
        (LLMError("per day", status=429, retry_after=3600.0), True),
        (LLMError("no headers", status=429), False),
    ],
)
def test_pool_is_exhausted_only_for_long_rate_limits(error, expected):
    assert pool_is_exhausted(error) is expected
