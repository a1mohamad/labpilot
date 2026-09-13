from __future__ import annotations

import logging

import pytest

from labpilot.embed import rates
from labpilot.embed.contracts import Rate

REQ = "x-ratelimit-limit-req-minute"
TOK = "x-ratelimit-limit-tokens-minute"


@pytest.fixture(autouse=True)
def clean():
    """Module state that leaks between tests is a shared fixture.

    _OBSERVED lives for the whole process, so without this a test that feeds a
    fake header changes what every LATER test sees - and the suite quietly
    starts depending on the order it runs in. Same shape as the 2026-09-04
    flake, where every run shared one schema name and two runs deleted each
    other's tables.
    """
    rates.forget()
    yield
    rates.forget()


def test_a_limit_the_provider_reports_is_remembered():
    rates.learn("m", {REQ: "60"})

    assert rates.observed("m") == {"requests_per_minute": 60}


def test_a_model_we_never_called_has_nothing_observed():
    assert rates.observed("never-called") == {}


def test_both_limits_are_learned_when_both_are_sent():
    rates.learn("m", {REQ: "60", TOK: "50000"})

    assert rates.observed("m") == {
        "requests_per_minute": 60,
        "tokens_per_minute": 50_000,
    }


def test_a_provider_that_sends_no_rate_header_teaches_us_nothing():
    """Google sends none at all, measured 2026-09-13.

    So for Google the declared seed is the only source there will ever be,
    and this is what would notice if learn() ever started inventing one.
    """
    rates.learn("gemini-embedding-001", {"content-type": "application/json"})

    assert rates.observed("gemini-embedding-001") == {}


def test_a_header_that_is_not_a_number_is_ignored():
    rates.learn("m", {REQ: "soon"})

    assert rates.observed("m") == {}


def test_a_limit_of_zero_is_ignored():
    """`limit: 0` means NOT ENTITLED, never "zero requests a minute".

    The LLM layer learned this from GLM-5.2 on 2026-08-16: a ceiling of zero
    says the model is not on this account's plan. Storing it as a rate would
    make minutes() treat the model as infinitely slow - a plausible-looking
    number for something that is really unavailable.
    """
    rates.learn("m", {REQ: "0"})

    assert rates.observed("m") == {}


def test_a_reported_limit_that_contradicts_the_seed_warns(caplog):
    """The whole reason learn() is given the declared rate.

    Letting observation override a seed SILENTLY would be worse than
    hardcoding it: a wrong constant would be quietly replaced and nobody would
    ever learn it was wrong. This is the same job _validated() does when a real
    vector's width contradicts the declared `dim`.
    """
    with caplog.at_level(logging.WARNING):
        rates.learn("m", {REQ: "30"}, Rate(requests_per_minute=60))

    assert "the seed is stale" in caplog.text
    assert rates.observed("m") == {"requests_per_minute": 30}


def test_a_reported_limit_that_agrees_with_the_seed_is_quiet(caplog):
    with caplog.at_level(logging.WARNING):
        rates.learn("m", {REQ: "60"}, Rate(requests_per_minute=60))

    assert "stale" not in caplog.text
