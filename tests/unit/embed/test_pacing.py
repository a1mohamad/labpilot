from __future__ import annotations

import pytest

from labpilot.embed import pacing
from labpilot.embed.contracts import Pace

# caps after the 0.9 headroom: 900 tokens and 9 texts a minute
PACE = Pace(tokens_per_minute=1_000, texts_per_minute=10)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def _fresh():
    pacing.forget()
    yield
    pacing.forget()


def book(clock, *, tokens, texts=1, pool="p"):
    return pacing.reserve(
        pool, PACE, tokens=tokens, texts=texts, clock=clock, sleep=clock.sleep
    )


def test_a_request_that_fits_the_minute_goes_at_once():
    clock = Clock()
    assert book(clock, tokens=500) == 0
    assert clock.slept == []


def test_a_request_that_would_overfill_the_minute_waits_for_the_oldest_to_leave():
    clock = Clock()
    book(clock, tokens=500)
    clock.now += 10
    assert book(clock, tokens=500) == pytest.approx(52.0)  # 62 - 10


def test_the_window_outlasts_a_minute():
    # we stamp a request when it LEAVES and Google when it ARRIVES, so at 60
    # seconds our window must still hold it
    clock = Clock()
    book(clock, tokens=500)
    clock.now += 60
    assert book(clock, tokens=500) == pytest.approx(2.0)


def test_texts_bind_even_when_tokens_have_room():
    # Google's 100 a minute counts TEXTS, and a batch of short texts hits it
    # long before the token limit
    clock = Clock()
    book(clock, tokens=10, texts=5)
    assert book(clock, tokens=10, texts=5) > 0


def test_an_empty_window_admits_a_request_larger_than_the_minute():
    # otherwise it would wait forever
    clock = Clock()
    assert book(clock, tokens=5_000) == 0


def test_two_pools_never_share_a_minute():
    # Google bills per project per MODEL: one model's spend must not slow another
    clock = Clock()
    book(clock, tokens=800, pool="GOOGLE_API_KEY:model-a")
    assert book(clock, tokens=800, pool="GOOGLE_API_KEY:model-b") == 0
