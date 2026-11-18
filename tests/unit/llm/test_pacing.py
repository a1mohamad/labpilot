import pytest

from labpilot.llm import CHAIN, _pacing, tiers


class FakeClock:
    """A clock that only moves when the test moves it."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(_pacing, "time", fake)
    return fake


def enter(account="A", *, concurrent=None, gap=0.0, max_wait=2.0):
    return _pacing.enter(account, concurrent=concurrent, gap=gap, max_wait=max_wait)


# ---- the rest between two calls (LiteRouter: 8 seconds) ----------------------


def test_the_first_call_on_an_account_is_admitted_at_once(clock):
    assert enter(gap=8.0) == (None, 0.0)


def test_a_call_inside_a_short_rest_is_admitted_with_the_rest_to_sleep(clock):
    enter(gap=8.0)
    clock.now += 7.0

    reason, rest = enter(gap=8.0)

    assert reason is None
    assert rest == pytest.approx(1.0)


def test_a_call_inside_a_long_rest_is_refused_and_nothing_is_reserved(clock):
    enter(gap=8.0)
    clock.now += 3.0

    reason, rest = enter(gap=8.0)

    assert reason is not None and "must rest" in reason
    assert rest == 0.0
    # The refused call took no turn: at second 8 the account is free again.
    clock.now += 5.0
    assert enter(gap=8.0) == (None, 0.0)


def test_a_call_after_the_gap_is_admitted_at_once(clock):
    enter(gap=8.0)
    clock.now += 8.0

    assert enter(gap=8.0) == (None, 0.0)


def test_two_accounts_do_not_rest_for_each_other(clock):
    enter("A", gap=8.0)

    assert enter("B", gap=8.0) == (None, 0.0)


def test_two_calls_at_the_same_moment_get_two_different_turns(clock):
    # The first takes the turn, so the second sees the account resting.
    assert enter(gap=1.5, max_wait=2.0)[0] is None
    reason, rest = enter(gap=1.5, max_wait=2.0)

    assert reason is None
    assert rest == pytest.approx(1.5)


def test_with_no_limit_the_account_keeps_no_state(clock):
    enter(gap=0.0)
    enter(gap=0.0)

    assert _pacing._next_free == {}
    assert _pacing._open_calls == {}


# ---- how many calls may be open at once (LiteRouter and Requesty: one) -------


def test_a_second_call_is_refused_while_the_first_is_open(clock):
    assert enter(concurrent=1)[0] is None

    reason, _ = enter(concurrent=1)

    assert reason is not None and "only 1 at a time" in reason


def test_the_place_is_free_again_after_the_call_ends(clock):
    enter(concurrent=1)
    _pacing.leave("A", concurrent=1, quiet=0.0)

    assert enter(concurrent=1) == (None, 0.0)


def test_a_refused_call_does_not_take_a_place(clock):
    enter(concurrent=1)
    enter(concurrent=1)  # refused
    _pacing.leave("A", concurrent=1, quiet=0.0)  # the one open call ends

    assert enter(concurrent=1) == (None, 0.0)


def test_two_accounts_have_their_own_places(clock):
    enter("A", concurrent=1)

    assert enter("B", concurrent=1) == (None, 0.0)


def test_with_no_limit_any_number_of_calls_are_open(clock):
    assert [enter(concurrent=None)[0] for _ in range(5)] == [None] * 5


def test_leaving_more_often_than_entering_never_goes_below_zero(clock):
    _pacing.leave("A", concurrent=1, quiet=0.0)
    _pacing.leave("A", concurrent=1, quiet=0.0)

    assert enter(concurrent=1) == (None, 0.0)
    assert enter(concurrent=1)[0] is not None


def test_the_account_is_quiet_for_a_moment_after_a_call_ends(clock):
    enter(concurrent=1)
    _pacing.leave("A", concurrent=1, quiet=1.0)

    reason, rest = enter(concurrent=1, max_wait=2.0)

    assert reason is None
    assert rest == pytest.approx(1.0)


# ---- the provider does not pace itself any more ------------------------------


def test_a_provider_sends_its_call_at_once_and_leaves_the_pacing_to_the_chain(
    monkeypatch,
):
    # complete() used to sleep for the rest of the gap. Now the chain decides, in
    # one place, whether to call at all, so a direct call is never delayed twice.
    import responses

    provider = tiers.LITEROUTER_GLM_5_3_FLASH
    monkeypatch.setenv("LITEROUTER_API_KEY", "key")
    slept = []
    monkeypatch.setattr("time.sleep", slept.append)

    with responses.RequestsMock() as mock:
        mock.post(
            provider.url,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )
        provider.complete("hello")
        provider.complete("hello again")

    assert slept == []


# ---- the limits written in the registry --------------------------------------


def test_one_call_at_a_time_belongs_to_literouter_and_requesty_only():
    one = {"LITEROUTER_API_KEY", "REQUESTY_API_KEY"}
    for tier in CHAIN:
        expected = 1 if tier.api_key_env in one else None
        assert tier.max_concurrent == expected, tier.name


def test_literouter_rests_8_seconds_between_calls_and_1_second_after_one():
    for tier in CHAIN:
        if tier.api_key_env == "LITEROUTER_API_KEY":
            assert tier.seconds_between_calls == 8.0, tier.name
            assert tier.seconds_after_call == 1.0, tier.name
        else:
            assert tier.seconds_after_call == 0.0, tier.name
