"""D130: a late call gets help, a failed tier rests, and nothing waits for it."""

import threading
import time

import pytest

from labpilot.llm import _health, _pacing
from labpilot.llm._stream import cancel_token
from labpilot.llm.chain import LLMClient
from labpilot.llm.contracts import LLMResult
from labpilot.llm.errors import AllFreeTiersExhausted, LLMError


class Tier:
    """Answers after `seconds`, or raises, and ends at once when it is cancelled."""

    def __init__(self, name, *, seconds=0.0, error=None, key=None, model=None, **kw):
        self.name = name
        self.tier = 1
        self.api_key_env = key or f"KEY_{name}"
        self.model = model or name
        self.max_concurrent = kw.get("max_concurrent")
        self.seconds, self.error = seconds, error
        self.calls = 0
        self.cancelled = threading.Event()

    @property
    def pool(self):
        return f"{self.api_key_env}:{self.model}"

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.calls += 1
        token = cancel_token.get()
        end = time.monotonic() + self.seconds
        while time.monotonic() < end:
            if token.done:
                self.cancelled.set()
                raise LLMError("cancelled", retryable=False)
            time.sleep(0.005)
        if self.error is not None:
            raise self.error
        return LLMResult(text=self.name, model=self.model, tier=self.tier)


def ask(*tiers, **kw):
    kw.setdefault("hedge_after", 0.1)
    kw.setdefault("retry_delays", ())
    return LLMClient(chain=tiers, **kw).generate("hello")


def test_a_late_call_gets_a_second_tier_beside_it_and_the_first_answer_wins():
    slow, fast = Tier("slow", seconds=5), Tier("fast")
    started = time.monotonic()

    assert ask(slow, fast).text == "fast"

    assert time.monotonic() - started < 2
    assert slow.cancelled.wait(2)  # the loser is ended, not left to write on


def test_a_call_in_time_gets_no_help():
    first, second = Tier("first", seconds=0.02), Tier("second")

    assert ask(first, second, hedge_after=1.0).text == "first"
    assert second.calls == 0


def test_with_no_hedge_a_slow_call_is_waited_for():
    slow, fast = Tier("slow", seconds=0.3), Tier("fast")

    assert ask(slow, fast, hedge_after=None).text == "slow"
    assert fast.calls == 0


def test_the_first_call_still_wins_when_it_ends_first():
    first, helper = Tier("first", seconds=0.3), Tier("helper", seconds=5)

    assert ask(first, helper).text == "first"
    assert helper.cancelled.wait(2)


def test_help_is_never_the_same_model_or_the_same_account():
    slow = Tier("slow", seconds=5, key="K1", model="m")
    twin = Tier("twin", key="K2", model="m")
    sibling = Tier("sibling", key="K1", model="n")
    other = Tier("other")

    assert ask(slow, twin, sibling, other).text == "other"
    assert (twin.calls, sibling.calls) == (0, 0)


def test_at_most_three_calls_are_open_at_once():
    tiers = [Tier(str(n), seconds=1.0) for n in range(5)]

    ask(*tiers)

    assert [t.calls for t in tiers] == [1, 1, 1, 0, 0]


def test_a_tier_that_was_resting_is_asked_again_in_the_same_call_when_it_is_free(
    monkeypatch,
):
    monkeypatch.setattr("labpilot.llm._race.LOOK_AGAIN", 0.05)
    best, slow = Tier("best"), Tier("slow", seconds=5)
    _health.rest("best", (0.3, 0.3))

    assert ask(best, slow).text == "best"


def test_a_failed_helper_is_followed_by_another_one():
    slow = Tier("slow", seconds=5)
    broken = Tier("broken", error=LLMError("x", status=404))
    good = Tier("good")

    assert ask(slow, broken, good).text == "good"


def test_a_rejected_answer_does_not_end_the_race():
    wrong, right = Tier("wrong"), Tier("right")
    client = LLMClient(chain=(wrong, right), retry_delays=())

    result = client.generate(
        "hi", problem_with=lambda r: "no" if r.text == "wrong" else None
    )

    assert result.text == "right"


def test_a_spent_tier_is_not_asked_again_by_the_next_call():
    spent = Tier("spent", error=LLMError("x", status=429, retry_after=3600.0))
    good = Tier("good")

    ask(spent, good)
    result = ask(spent, good)

    assert spent.calls == 1
    assert "exhausted" in result.attempts[0].error


def test_a_resting_tier_is_the_last_resort_of_a_call_that_has_nothing_else():
    only = Tier("only")
    _health.rest("only", (30.0, 30.0))

    assert ask(only).text == "only"


def test_a_spent_quota_is_not_even_the_last_resort():
    only = Tier("only")
    _health.rest(only.pool, (3600.0, 3600.0))

    with pytest.raises(AllFreeTiersExhausted):
        ask(only)
    assert only.calls == 0


def test_a_busy_tier_is_asked_after_all_when_nothing_else_answers():
    busy = Tier("busy", max_concurrent=1)
    broken = Tier("broken", seconds=0.2, error=LLMError("x", status=404))
    _pacing.enter("KEY_busy", concurrent=1, gap=0.0, max_wait=0.0)
    threading.Timer(
        0.1, lambda: _pacing.leave("KEY_busy", concurrent=1, quiet=0.0)
    ).start()

    assert ask(busy, broken, hedge_after=None).text == "busy"


def test_after_a_silent_model_its_other_keys_are_asked_last():
    silent = Tier("silent", model="m", error=LLMError("x", retryable=False, slow=True))
    twin, other = Tier("twin", model="m"), Tier("other")

    assert ask(silent, twin, other).text == "other"


def test_a_cut_call_rests_its_tier_and_the_walk_goes_on():
    stuck, good = Tier("stuck", seconds=5), Tier("good")

    assert ask(stuck, good, hedge_after=None, call_stop=0.1).text == "good"
    assert _health.left("stuck") > 0


def test_the_budget_ends_a_generate_with_every_call_open():
    slow, slower = Tier("slow", seconds=5), Tier("slower", seconds=5)
    started = time.monotonic()

    with pytest.raises(AllFreeTiersExhausted):
        ask(slow, slower, total_budget=0.3)

    assert time.monotonic() - started < 2
    assert slow.cancelled.wait(2)
    assert slower.cancelled.wait(2)


def test_a_loser_frees_the_one_slot_of_its_account():
    slow, fast = Tier("slow", seconds=5, max_concurrent=1), Tier("fast")

    ask(slow, fast)

    assert slow.cancelled.wait(2)
    time.sleep(0.05)
    reason, _ = _pacing.enter("KEY_slow", concurrent=1, gap=0.0, max_wait=0.0)
    assert reason is None


def test_a_bug_in_a_provider_does_not_hang_the_call():
    broken, good = Tier("broken", error=ValueError("bug")), Tier("good")

    assert ask(broken, good, hedge_after=None, call_stop=None).text == "good"
