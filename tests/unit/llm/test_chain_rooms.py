from __future__ import annotations

import pytest

from labpilot.llm import _rooms
from labpilot.llm.chain import LLMClient
from labpilot.llm.contracts import LLMResult
from labpilot.llm.errors import AllFreeTiersExhausted, LLMError

# 300 characters are 100 estimated tokens, and about 110 with the safety margin.
PROMPT = "x" * 300


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(_rooms, "time", fake)
    monkeypatch.setattr("labpilot.llm.chain.time", fake)
    return fake


class RoomProvider:
    """A tier with its own room: 1,000 input tokens a minute, 900 bookable."""

    api_key_env = "KEY"

    def __init__(
        self,
        pool,
        *,
        tier=1,
        outcome="answer",
        max_input_tokens=1_000,
        requests_per_minute=None,
    ):
        self.name = pool
        self.tier = tier
        self.quota_pool = pool
        self.outcome = outcome
        self.max_input_tokens = max_input_tokens
        self.requests_per_minute = requests_per_minute
        self.calls = 0

    @property
    def pool(self):
        return self.quota_pool

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return LLMResult(text=self.outcome, model=self.name, tier=self.tier)


class PlainProvider:
    """A tier with no limits at all, like most of the chain."""

    name = "Plain"
    tier = 1
    api_key_env = "PLAIN_KEY"
    pool = "PLAIN_KEY"

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        return LLMResult(text="answer", model=self.name, tier=self.tier)


def fill(pool: str, tokens: int = 850) -> None:
    _rooms.book(pool, tokens=tokens, token_limit=1_000, request_limit=None)


def test_a_full_room_is_skipped_and_the_next_key_answers(clock):
    first, second = RoomProvider("P1", tier=1), RoomProvider("P2", tier=2)
    fill("P1")

    result = LLMClient(chain=(first, second)).generate(PROMPT)

    assert result.tier == 2
    assert first.calls == 0
    assert result.attempts[0].error.startswith("skipped: room full")
    assert clock.slept == []


def test_when_every_room_is_full_the_walk_ends_at_once_and_waits_for_nobody(clock):
    first, second = RoomProvider("P1", tier=1), RoomProvider("P2", tier=2)
    fill("P1")
    clock.now = 1_030.0
    fill("P2")
    clock.now = 1_040.0

    with pytest.raises(AllFreeTiersExhausted) as caught:
        LLMClient(chain=(first, second)).generate(PROMPT)

    # P1 would be free in 20 seconds. The old walk waited for it; now it is a
    # skip, like every other tier that cannot answer right now.
    assert clock.slept == []
    assert first.calls == 0 and second.calls == 0
    assert all(a.error.startswith("skipped: room full") for a in caught.value.attempts)


def test_a_failed_call_still_uses_up_its_room(clock):
    first = RoomProvider("P1", outcome=LLMError("P1: it failed", retryable=False))

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=(first,)).generate(PROMPT)

    # About 110 tokens are booked, so 800 more (910 in all) do not fit the 900.
    assert _rooms.book("P1", tokens=800, token_limit=1_000, request_limit=None) > 0.0


def test_a_tier_with_no_limits_never_touches_a_room(clock):
    LLMClient(chain=(PlainProvider(),)).generate(PROMPT)

    assert _rooms._ROOMS == {}


def test_a_tier_that_failed_is_asked_up_to_three_times_and_a_full_room_not_at_all(
    clock,
):
    broken = RoomProvider("P1", tier=1, outcome=LLMError("P1: it failed"))
    full = RoomProvider("P2", tier=2)
    fill("P2")

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=(broken, full)).generate(PROMPT)

    assert broken.calls == 3
    assert full.calls == 0


def test_the_request_limit_alone_can_fill_a_room(clock):
    first = RoomProvider("P1", tier=1, max_input_tokens=None, requests_per_minute=2)
    second = RoomProvider("P2", tier=2)
    client = LLMClient(chain=(first, second))

    tiers = [client.generate(PROMPT).tier for _ in range(3)]

    # 90% of 2 requests is 1, so the second call already moves on.
    assert tiers == [1, 2, 2]
