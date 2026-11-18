from __future__ import annotations

import threading
import time

import pytest

from labpilot.llm import _pacing
from labpilot.llm.chain import (
    LLMClient,
    model_is_unavailable,
    pool_is_exhausted,
    wait_before_retry,
    worth_a_second_try,
)
from labpilot.llm.contracts import LLMResult
from labpilot.llm.defaults import RETRY_DELAYS
from labpilot.llm.errors import AllFreeTiersExhausted, LLMError


class FakeProvider:
    def __init__(
        self,
        *,
        name,
        tier,
        api_key_env="KEY_A",
        outcomes,
        quota_pool=None,
        max_concurrent=None,
        seconds_between_calls=0.0,
        seconds_after_call=0.0,
    ):
        self.name = name
        self.tier = tier
        self.api_key_env = api_key_env
        self.quota_pool = quota_pool
        self.max_concurrent = max_concurrent
        self.seconds_between_calls = seconds_between_calls
        self.seconds_after_call = seconds_after_call
        self.outcomes = list(outcomes)
        self.calls = 0

    @property
    def pool(self):
        return self.quota_pool or self.api_key_env

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else self.outcomes_default
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(text=outcome, model=self.name, tier=self.tier)

    outcomes_default = LLMError("no outcome left")


def ok(name, tier, *, key="KEY_A", **kw):
    return FakeProvider(
        name=name, tier=tier, api_key_env=key, outcomes=["answer"], **kw
    )


def fails(name, tier, error, *, key="KEY_A", times=3, **kw):
    # The same error again and again: a tier is asked up to three times.
    return FakeProvider(
        name=name, tier=tier, api_key_env=key, outcomes=[error] * times, **kw
    )


# ---- the retry rule: 1 second, 3 seconds, then the next tier -----------------


def test_the_delays_are_one_and_three_seconds():
    assert RETRY_DELAYS == (1.0, 3.0)


def test_first_tier_answers_without_touching_the_rest():
    second = ok("Second", 2)
    result = LLMClient(chain=(ok("First", 1), second)).generate("hello")

    assert result.tier == 1
    assert result.attempts == ()
    assert second.calls == 0


def test_a_tier_that_does_not_answer_is_asked_again_after_1s_and_after_3s(no_sleep):
    first = fails("First", 1, LLMError("First: connection reset"))
    second = ok("Second", 2, key="KEY_B")

    result = LLMClient(chain=(first, second)).generate("hello")

    assert result.tier == 2
    assert first.calls == 3
    assert no_sleep == [1.0, 3.0]
    assert [a.tier for a in result.attempts] == [1]


def test_a_tier_that_answers_on_the_second_try_is_kept(no_sleep):
    first = FakeProvider(
        name="First", tier=1, outcomes=[LLMError("busy", status=503), "answer"]
    )
    second = ok("Second", 2, key="KEY_B")

    result = LLMClient(chain=(first, second)).generate("hello")

    assert result.tier == 1
    assert first.calls == 2
    assert second.calls == 0
    assert no_sleep == [1.0]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_busy_or_failing_server_is_asked_again(status, no_sleep):
    first = fails("First", 1, LLMError("x", status=status))

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=(first,)).generate("hello")

    assert first.calls == 3
    assert no_sleep == [1.0, 3.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_a_refusal_that_cannot_change_is_not_asked_again(status, no_sleep):
    first = fails("First", 1, LLMError("x", status=status))
    second = ok("Second", 2, key="KEY_B")

    result = LLMClient(chain=(first, second)).generate("hello")

    assert result.tier == 2
    assert first.calls == 1
    assert no_sleep == []


def test_a_call_refused_locally_is_not_asked_again(no_sleep):
    first = fails("First", 1, LLMError("too big", retryable=False))
    second = ok("Second", 2, key="KEY_B")

    result = LLMClient(chain=(first, second)).generate("hello")

    assert result.tier == 2
    assert first.calls == 1
    assert no_sleep == []


def test_a_provider_that_says_come_back_later_is_not_waited_for(no_sleep):
    # 30 seconds is far more than the 3 seconds the walk is willing to wait.
    first = fails("First", 1, LLMError("busy", status=429, retry_after=30.0))
    second = ok("Second", 2, key="KEY_B")

    result = LLMClient(chain=(first, second)).generate("hello")

    assert result.tier == 2
    assert first.calls == 1
    assert no_sleep == []


def test_a_short_retry_after_is_kept_when_it_is_longer_than_the_fixed_delay(
    no_sleep,
):
    first = FakeProvider(
        name="First",
        tier=1,
        outcomes=[LLMError("busy", status=429, retry_after=2.0), "answer"],
    )

    LLMClient(chain=(first,)).generate("hello")

    assert no_sleep == [2.0]


def test_a_daily_limit_retires_every_tier_of_the_pool_at_once(no_sleep):
    daily = LLMError("daily cap", status=429, reset_at=time.time() + 3600)
    third = ok("Third", 3, key="POOL")
    client = LLMClient(
        chain=(
            fails("First", 1, daily, key="POOL"),
            fails("Second", 2, LLMError("boom", retryable=False), key="OTHER"),
            third,
            ok("Fourth", 4, key="LAST"),
        )
    )
    result = client.generate("hello")

    assert result.tier == 4
    assert third.calls == 0
    assert "exhausted" in result.attempts[2].error
    assert no_sleep == []


def test_a_model_that_is_not_on_the_plan_is_skipped_without_retry(no_sleep):
    no_plan = LLMError("limit 0", status=429, rate_limit=0)
    first = fails("First", 1, no_plan, key="POOL")
    second = ok("Second", 2, key="POOL")

    result = LLMClient(chain=(first, second)).generate("hello")

    assert result.tier == 2
    assert first.calls == 1
    assert "not available on this account" in result.attempts[0].error


def test_raises_all_free_tiers_exhausted_carrying_every_attempt(no_sleep):
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


def test_a_spent_time_budget_skips_every_tier_and_calls_nobody():
    first = ok("First", 1)

    with pytest.raises(AllFreeTiersExhausted) as caught:
        LLMClient(chain=(first,), total_budget=0.0).generate("hello")

    assert first.calls == 0
    assert "time budget spent" in caught.value.attempts[0].error


def test_a_retry_that_would_pass_the_time_budget_is_not_made(monkeypatch, no_sleep):
    first = fails("First", 1, LLMError("x", status=503))
    clock = {"now": 0.0}
    monkeypatch.setattr("labpilot.llm.chain.time.monotonic", lambda: clock["now"])

    def spend(seconds):
        clock["now"] += seconds

    no_sleep.clear()
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", spend)

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=(first,), total_budget=0.5).generate("hello")

    # 0 + 1 s of waiting would be past the 0.5 s budget: one call, no retry.
    assert first.calls == 1


# ---- the answer the caller rejects ---------------------------------------


def test_a_rejected_answer_goes_to_the_next_tier_and_is_not_asked_again(no_sleep):
    first = FakeProvider(name="First", tier=1, outcomes=["bad", "bad", "bad"])
    second = FakeProvider(name="Second", tier=2, outcomes=["good"], api_key_env="B")

    result = LLMClient(chain=(first, second)).generate(
        "hello", problem_with=lambda r: "wrong" if r.text == "bad" else None
    )

    assert result.text == "good"
    assert first.calls == 1
    assert no_sleep == []
    assert "answer rejected" in result.attempts[0].error


# ---- a call that hangs ----------------------------------------------------


class Hanging(FakeProvider):
    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.calls += 1
        threading.Event().wait(5)  # an HTTP call that never ends
        return LLMResult(text="late", model=self.name, tier=self.tier)


def test_a_call_that_hangs_is_given_up_and_not_asked_again(no_sleep):
    hang = Hanging(name="Hang", tier=1, outcomes=[])
    second = ok("Second", 2, key="KEY_B")

    started = time.monotonic()
    result = LLMClient(chain=(hang, second), call_stop=0.2).generate("hello")

    assert result.tier == 2
    assert hang.calls == 1
    assert time.monotonic() - started < 2.0
    assert "no answer after" in result.attempts[0].error
    assert no_sleep == []


def test_with_no_stop_the_call_runs_in_the_calling_thread():
    seen = []

    class Where(FakeProvider):
        def complete(self, prompt, *, max_tokens=1024, tool=None):
            seen.append(threading.current_thread())
            return LLMResult(text="x", model=self.name, tier=self.tier)

    LLMClient(chain=(Where(name="W", tier=1, outcomes=[]),), call_stop=None).generate(
        "a"
    )

    assert seen == [threading.current_thread()]


def test_a_stopped_call_carries_the_error_of_a_failed_one(no_sleep):
    first = fails("First", 1, LLMError("boom", status=404))

    with pytest.raises(AllFreeTiersExhausted) as caught:
        LLMClient(chain=(first,), call_stop=5.0).generate("hello")

    assert "boom" in caught.value.attempts[0].error


# ---- a busy account is skipped, never waited for -------------------------


def test_a_tier_that_takes_one_call_at_a_time_is_skipped_while_one_is_open(no_sleep):
    one_at_a_time = ok("Lite", 1, key="LITE", max_concurrent=1)
    second = ok("Second", 2, key="OTHER")
    _pacing.enter("LITE", concurrent=1, gap=0.0, max_wait=0.0)  # another call is open

    result = LLMClient(chain=(one_at_a_time, second)).generate("hello")

    assert result.tier == 2
    assert one_at_a_time.calls == 0
    assert result.attempts[0].error.startswith("skipped: LITE")
    assert no_sleep == []


def test_the_place_is_given_back_when_the_call_fails(no_sleep):
    lite = fails("Lite", 1, LLMError("x", status=404), key="LITE", max_concurrent=1)
    other = ok("Other", 2, key="OTHER")

    LLMClient(chain=(lite, other)).generate("hello")

    reason, _ = _pacing.enter("LITE", concurrent=1, gap=0.0, max_wait=0.0)
    assert reason is None


def test_an_account_that_must_rest_longer_than_the_limit_is_skipped(no_sleep):
    lite = ok("Lite", 1, key="LITE", seconds_between_calls=8.0)
    second = ok("Second", 2, key="OTHER")

    client = LLMClient(chain=(lite, second))
    assert client.generate("hello").tier == 1
    result = client.generate("hello")  # 8 seconds have not passed

    assert result.tier == 2
    assert lite.calls == 1
    assert "must rest" in result.attempts[0].error
    assert no_sleep == []


def test_the_account_is_quiet_for_a_moment_after_a_call_ends(no_sleep):
    lite = ok("Lite", 1, key="LITE", seconds_after_call=1.0)

    LLMClient(chain=(lite,)).generate("hello")

    # The quiet second is shorter than the longest rest the walk will take.
    reason, rest = _pacing.enter("LITE", concurrent=None, gap=0.0, max_wait=2.0)
    assert reason is None
    assert 0.0 < rest <= 1.0


# ---- the small rules of the retry ----------------------------------------


def test_worth_a_second_try():
    assert worth_a_second_try(LLMError("reset"))
    assert worth_a_second_try(LLMError("x", status=503))
    assert not worth_a_second_try(LLMError("x", status=404))
    assert not worth_a_second_try(LLMError("x", retryable=False))
    daily = LLMError("x", status=429, reset_at=time.time() + 3600)
    assert not worth_a_second_try(daily)
    assert not worth_a_second_try(LLMError("x", status=429, rate_limit=0))


def test_wait_before_retry():
    assert wait_before_retry(LLMError("x"), 0) == 1.0
    assert wait_before_retry(LLMError("x"), 1) == 3.0
    assert wait_before_retry(LLMError("x"), 2) is None
    assert wait_before_retry(LLMError("x", retry_after=2.0), 0) == 2.0
    assert wait_before_retry(LLMError("x", retry_after=4.0), 0) is None
    reset = LLMError("x", reset_at=time.time() + 2.0)
    assert 1.0 <= wait_before_retry(reset, 0) <= 2.0


def test_pool_and_plan_rules_are_unchanged():
    assert pool_is_exhausted(LLMError("x", status=429, retry_after=120.0))
    assert not pool_is_exhausted(LLMError("x", status=429, retry_after=5.0))
    assert not pool_is_exhausted(LLMError("x", status=503, retry_after=500.0))
    assert model_is_unavailable(LLMError("x", status=429, rate_limit=0))
    assert not model_is_unavailable(LLMError("x", status=429, rate_limit=10))


# ---- the errors the providers raise carry the right "retryable" -------------


def test_a_prompt_refused_locally_says_a_second_try_cannot_help():
    from labpilot.llm import tiers

    with pytest.raises(LLMError) as too_big:
        tiers.GEMMA_4_26B._check_fits("x" * 100_000, 100)
    with pytest.raises(LLMError) as too_long:
        tiers.GEMMA_4_26B._check_fits("hello", 10_000_000)

    with pytest.raises(LLMError) as past_the_window:
        tiers.GPT_OSS_120B_GROQ._check_fits("x" * 30_000, 1_000)

    assert too_big.value.retryable is False
    assert too_long.value.retryable is False
    assert past_the_window.value.retryable is False


def test_a_missing_key_says_a_second_try_cannot_help(monkeypatch):
    from labpilot.llm import tiers

    monkeypatch.delenv(tiers.GEMMA_4_26B.api_key_env, raising=False)

    with pytest.raises(LLMError) as caught:
        tiers.GEMMA_4_26B._api_key()

    assert caught.value.retryable is False


def test_an_answer_that_cannot_be_read_says_a_second_try_cannot_help():
    from labpilot.llm._calls import read_arguments, read_object

    for read, raw in (
        (read_object, "no json here"),
        (read_object, "{broken"),
        (read_arguments, "{broken"),
        (read_arguments, 5),
    ):
        with pytest.raises(LLMError) as caught:
            read(raw, "Tier")
        assert caught.value.retryable is False


def test_a_client_can_be_told_not_to_retry_at_all(no_sleep):
    # A measurement of one model alone wants the first answer or the first failure.
    first = fails("First", 1, LLMError("x", status=503))

    with pytest.raises(AllFreeTiersExhausted):
        LLMClient(chain=(first,), retry_delays=()).generate("hello")

    assert first.calls == 1
    assert no_sleep == []
