import pytest

from labpilot.llm import _health
from labpilot.llm._failures import note_failure
from labpilot.llm._http import DAILY_REST, daily_rest
from labpilot.llm.errors import LLMError


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("labpilot.llm._health.time.monotonic", lambda: now[0])
    return now


def test_a_tier_rests_and_is_free_again(clock):
    _health.rest("T", (10.0, 100.0))
    assert _health.left("T") == 10.0
    clock[0] += 10.0
    assert _health.left("T") == 0.0


def test_each_failure_in_a_row_doubles_the_rest_up_to_the_longest(clock):
    lengths = []
    for _ in range(5):
        _health.rest("T", (10.0, 50.0))
        lengths.append(_health.left("T"))
        clock[0] += 1000.0
    assert lengths == [10.0, 20.0, 40.0, 50.0, 50.0]


def test_one_good_answer_ends_the_rest_and_the_strikes(clock):
    _health.rest("T", (10.0, 100.0))
    clock[0] += 1000.0
    _health.rest("T", (10.0, 100.0))
    _health.good("T")
    assert _health.left("T") == 0.0
    _health.rest("T", (10.0, 100.0))
    assert _health.left("T") == 10.0


def test_the_time_a_provider_asks_for_is_kept_but_never_more_than_a_day(clock):
    _health.rest("T", (10.0, 100.0), asked=5000.0)
    assert _health.left("T") == 5000.0
    _health.rest("U", (10.0, 100.0), asked=10_000_000.0)
    assert _health.left("U") == 86_400.0


def test_a_spent_quota_rests_the_pool_and_not_only_the_tier(clock):
    note_failure("T", "POOL", LLMError("x", status=429, retry_after=300.0))
    assert _health.left("POOL") == 300.0
    assert _health.left("T") == 0.0


def test_a_silent_tier_rests_and_its_pool_does_not(clock):
    note_failure("T", "POOL", LLMError("x", retryable=False, slow=True))
    assert _health.left("T") == _health.SLOW[0]
    assert _health.left("POOL") == 0.0


def test_an_overloaded_tier_rests_shortly(clock):
    note_failure("T", "POOL", LLMError("x", status=503))
    assert _health.left("T") == _health.OVERLOADED[0]


@pytest.mark.parametrize("status", [401, 402, 404])
def test_a_tier_that_is_gone_rests_long(clock, status):
    note_failure("T", "POOL", LLMError("x", status=status))
    assert _health.left("T") == _health.GONE[0]


def test_a_refusal_of_our_own_rests_nothing(clock):
    # Too long, or an answer that could not be read: it says nothing about the
    # next call.
    note_failure("T", "POOL", LLMError("too long", retryable=False))
    assert [_health.left(k) for k in ("T", "POOL")] == [0.0, 0.0]


@pytest.mark.parametrize(
    "body",
    [
        '{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}',
        "you have used up your daily free allocation of 10,000 neurons",
        "Your free allowance for ':free' models is used",
    ],
)
def test_a_429_that_says_the_day_is_spent_in_its_body_rests_the_pool_long(body):
    assert daily_rest(429, body, None) == DAILY_REST
    assert daily_rest(429, body, 2.0) == DAILY_REST


def test_a_429_for_a_minute_keeps_what_it_asks_for():
    assert daily_rest(429, "requests per minute", 12.0) == 12.0
    assert daily_rest(503, "daily", None) is None


def test_calls_that_fail_together_are_one_failure(clock):
    for _ in range(5):
        _health.rest("T", (10.0, 100.0))
    assert _health.left("T") == 10.0
