from __future__ import annotations

import pytest

from labpilot.llm import CHAIN, _rooms, tiers

URL = "https://provider.test/v1/chat/completions"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(_rooms, "time", fake)
    return fake


def book(pool: str, tokens: int = 0, *, token_limit=None, request_limit=None) -> float:
    return _rooms.book(
        pool, tokens=tokens, token_limit=token_limit, request_limit=request_limit
    )


def test_the_margin_adds_ten_percent_to_an_estimate():
    # 100 * 1.1 is 110.00000000000001 in floating point, so ceil gives 111. The
    # length check has always rounded this way; the test pins "about 10%".
    assert 110 <= _rooms.with_margin(100) <= 111


def test_a_room_admits_calls_until_its_tokens_are_used(clock):
    # 90% of 1,000 is 900.
    assert book("P", 400, token_limit=1_000) == 0.0
    assert book("P", 400, token_limit=1_000) == 0.0
    assert book("P", 400, token_limit=1_000) > 0.0


def test_a_room_keeps_a_tenth_of_the_published_limit_free(clock):
    assert book("P", 900, token_limit=1_000) == 0.0
    assert book("P", 1, token_limit=1_000) > 0.0


def test_a_full_room_books_nothing_and_says_how_long_to_wait(clock):
    book("P", 500, token_limit=1_000)
    clock.now = 1_020.0
    book("P", 400, token_limit=1_000)
    clock.now = 1_030.0

    wait = book("P", 300, token_limit=1_000)

    # The oldest call was booked at 1,000 and leaves the minute at 1,060.
    assert wait == 30.0
    assert len(_rooms._ROOMS["P"].booked) == 2


def test_space_comes_back_when_the_oldest_call_leaves_the_minute(clock):
    book("P", 500, token_limit=1_000)
    clock.now = 1_020.0
    book("P", 400, token_limit=1_000)

    clock.now = 1_059.0
    assert book("P", 300, token_limit=1_000) > 0.0
    clock.now = 1_060.0
    assert book("P", 300, token_limit=1_000) == 0.0
    # The call at 1,000 has left, and the new one is really booked (a wait of 0.0
    # that books nothing would let the chain send a call that no room counted).
    assert [tokens for _, tokens in _rooms._ROOMS["P"].booked] == [400, 300]


def test_an_empty_room_admits_a_prompt_larger_than_its_cap(clock):
    assert book("P", 5_000, token_limit=1_000) == 0.0


def test_the_request_limit_counts_calls_and_not_tokens(clock):
    # 90% of 5 requests is 4.
    for _ in range(4):
        assert book("P", 0, request_limit=5) == 0.0

    assert book("P", 0, request_limit=5) > 0.0


def test_each_pool_has_its_own_room(clock):
    book("A", 900, token_limit=1_000)

    assert book("A", 100, token_limit=1_000) > 0.0
    assert book("B", 100, token_limit=1_000) == 0.0


def test_a_pool_with_no_limits_keeps_no_state(clock):
    assert book("P", 50_000) == 0.0
    assert _rooms._ROOMS == {}


# --- the limits written in the registry ------------------------------------


def test_token_harbor_takes_sixty_requests_a_minute_and_any_number_at_once():
    harbor = [t for t in CHAIN if t.api_key_env == "TOKEN_HARBOR_API_KEY"]

    assert len(harbor) == 4
    for tier in harbor:
        assert tier.requests_per_minute == 60, tier.name
        assert tier.max_concurrent is None, tier.name


def test_both_gemma_models_have_a_room_on_every_key():
    gemma = [
        t
        for t in CHAIN
        if t.model in {tiers.GEMMA_4_26B.model, tiers.GEMMA_4_31B.model}
    ]

    assert len(gemma) == 6
    assert len({t.pool for t in gemma}) == 6
    for tier in gemma:
        assert tier.max_input_tokens == 16_000, tier.name
        assert tier.requests_per_minute == 30, tier.name


def test_every_mistral_small_model_takes_two_requests_a_minute():
    # Mistral Medium, Magistral and Devstral are dead tiers (limit 0), not small ones.
    small = {"Ministral 8B", "Mistral Nemo", "Ministral 14B", "Codestral"}
    mistral = [t for t in CHAIN if t.name in small]

    assert {t.name for t in mistral} == small
    for tier in mistral:
        assert tier.requests_per_minute == 2, tier.name


def test_mistral_nemo_shares_the_room_of_ministral_8b():
    # Every Nemo answer says ministral-8b-2512 and its bucket was already empty
    # after one 8B call (measured 2026-11-16).
    assert tiers.MISTRAL_NEMO.pool == tiers.MINISTRAL_8B.pool
    assert tiers.MINISTRAL_14B.pool != tiers.MINISTRAL_8B.pool


def test_routeway_takes_five_and_orcarouter_ten_requests_a_minute_for_the_account():
    for tier in CHAIN:
        if tier.api_key_env == "ROUTEWAY_API_KEY":
            assert tier.requests_per_minute == 5, tier.name
        if tier.api_key_env == "ORCAROUTER_API_KEY":
            assert tier.requests_per_minute == 10, tier.name
