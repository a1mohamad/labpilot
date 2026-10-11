import pytest
import responses

from labpilot.llm import LLMError, OpenAICompatibleProvider, _pacing

URL = "https://provider.test/v1/chat/completions"


class FakeClock:
    """A clock that only moves when somebody sleeps, so no test really waits."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(_pacing, "time", fake)
    monkeypatch.setattr(_pacing, "_next_free", {})
    return fake


def test_the_first_call_on_an_account_does_not_wait(clock):
    _pacing.wait_for_turn("ACCOUNT_A", 8.0)

    assert clock.slept == []


def test_a_second_call_inside_the_gap_waits_for_the_rest_of_it(clock):
    _pacing.wait_for_turn("ACCOUNT_A", 8.0)
    clock.now += 3.0

    _pacing.wait_for_turn("ACCOUNT_A", 8.0)

    assert clock.slept == [5.0]


def test_a_call_after_the_gap_does_not_wait(clock):
    _pacing.wait_for_turn("ACCOUNT_A", 8.0)
    clock.now += 8.5

    _pacing.wait_for_turn("ACCOUNT_A", 8.0)

    assert clock.slept == []


def test_two_accounts_do_not_wait_for_each_other(clock):
    _pacing.wait_for_turn("ACCOUNT_A", 8.0)

    _pacing.wait_for_turn("ACCOUNT_B", 8.0)

    assert clock.slept == []


def test_calls_queue_up_one_slot_each(clock):
    """Three calls at the same instant leave 0, 8 and 16 seconds apart.

    The slot is reserved BEFORE the sleep. If it were taken after, every caller
    would see "nobody has called yet" and all three would go out together.
    """
    for _ in range(3):
        _pacing.wait_for_turn("ACCOUNT_A", 8.0)

    assert clock.slept == [8.0, 8.0]


def test_a_gap_of_zero_never_waits_and_keeps_no_state(clock):
    _pacing.wait_for_turn("ACCOUNT_A", 0.0)
    _pacing.wait_for_turn("ACCOUNT_A", 0.0)

    assert clock.slept == []
    assert _pacing._next_free == {}


def _provider(**extra) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name="Test Provider",
        tier=1,
        url=URL,
        model="test/model",
        api_key_env="TEST_API_KEY",
        context_window=8_000,
        max_output_tokens=4_000,
        **extra,
    )


def _ok_body():
    return {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}


@responses.activate
def test_complete_waits_for_its_turn_before_it_sends(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret")
    responses.post(URL, json=_ok_body())
    sent_when_waiting: list[int] = []

    def record(account: str, gap: float) -> None:
        sent_when_waiting.append(len(responses.calls))
        assert (account, gap) == ("TEST_API_KEY", 8.0)

    monkeypatch.setattr("labpilot.llm.base.wait_for_turn", record)

    _provider(seconds_between_calls=8.0).complete("hello")

    assert sent_when_waiting == [0]
    assert len(responses.calls) == 1


@responses.activate
def test_a_prompt_refused_locally_does_not_use_up_the_turn(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret")
    taken: list[str] = []
    monkeypatch.setattr(
        "labpilot.llm.base.wait_for_turn", lambda account, gap: taken.append(account)
    )

    with pytest.raises(LLMError, match="context window"):
        _provider(seconds_between_calls=8.0).complete("x" * 40_000)

    assert taken == []
    assert len(responses.calls) == 0


@responses.activate
def test_a_missing_key_does_not_use_up_the_turn(monkeypatch):
    """Seventeen LiteRouter tiers with no key must fail at once, not after
    seventeen rests of 8 seconds each."""
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    taken: list[str] = []
    monkeypatch.setattr(
        "labpilot.llm.base.wait_for_turn", lambda account, gap: taken.append(account)
    )

    with pytest.raises(LLMError, match="TEST_API_KEY is not set"):
        _provider(seconds_between_calls=8.0).complete("hello")

    assert taken == []
    assert len(responses.calls) == 0


def test_a_provider_waits_for_nobody_unless_it_is_told_to():
    assert _provider().seconds_between_calls == 0.0
