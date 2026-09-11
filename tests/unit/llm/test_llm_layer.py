from __future__ import annotations

import time

import pytest
import responses
from responses import matchers

import labpilot.llm as llm
from labpilot.llm import CHAIN, LLMClient
from labpilot.llm.defaults import DEFAULT_TIMEOUT, DEFAULT_TOTAL_BUDGET


def gemini_url(provider):
    return f"{provider.url}/{provider.model}:generateContent"


TIER_1 = CHAIN[0]
TIER_1_KEY_2 = CHAIN[1]

# The first tier running a DIFFERENT model. Derived, never indexed: CHAIN[1]
# used to be a different model and is now the same one on the second account,
# which silently turned a two-model test into a two-key test.
ANOTHER_MODEL = next(p for p in CHAIN if p.model != TIER_1.model)

GOOGLE_TIER_1_URL = gemini_url(TIER_1)
ANOTHER_MODEL_URL = gemini_url(ANOTHER_MODEL)
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture
def keys(monkeypatch):
    """Every credential the chain reads, DERIVED from CHAIN, never listed.

    The hardcoded list this replaces went stale the moment a second Google
    account was added: GOOGLE_API_KEY_2 was missing, so tier 2 failed on "key
    is not set". It passed locally anyway, because an earlier test imported
    api/config.py, whose module-level load_dotenv put the real key into the
    environment for the rest of the session - so the suite was green on this
    machine and red in CI, where no .env exists.
    """
    for provider in CHAIN:
        monkeypatch.setenv(provider.api_key_env, "secret-key")
        account = getattr(provider, "account_env", None)
        if account:
            monkeypatch.setenv(account, "secret-account")


def gemini_body(text="from gemini"):
    return {
        "modelVersion": CHAIN[0].model,
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
    }


def openai_body(model, text="from an openai-shaped provider"):
    return {
        "model": model,
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
    }


def test_every_public_name_is_importable():
    missing = [name for name in llm.__all__ if not hasattr(llm, name)]

    assert not missing, missing


@responses.activate
def test_the_real_chain_returns_tier_one_when_google_answers(keys):
    responses.post(GOOGLE_TIER_1_URL, json=gemini_body())

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == 1
    assert result.text == "from gemini"
    assert result.attempts == ()


@responses.activate
def test_one_spent_google_model_does_not_skip_the_others(keys):
    """Google bills per model, so one spent model must not retire the rest.

    Both accounts of the leading model are spent here, because they share a
    URL and differ only by key - so the rescue has to come from a genuinely
    DIFFERENT model. Collapsing the pool onto the API key would mark every
    Google tier dead on the first 429 and this would fail.
    """
    responses.post(
        GOOGLE_TIER_1_URL,
        status=429,
        json={"error": "daily quota exceeded for this model"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
    )
    responses.post(ANOTHER_MODEL_URL, json=gemini_body("a different model"))

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == ANOTHER_MODEL.tier
    assert result.text == "a different model"
    assert [attempt.tier for attempt in result.attempts] == [1, 2]


@responses.activate
def test_a_spent_model_falls_through_to_the_second_google_account(keys, monkeypatch):
    """The entire point of the second account, and nothing covered it.

    The two tiers are the SAME model on two keys, so they share a URL and can
    only be told apart by the header. Key 1 is spent; key 2 must answer - it is
    a separate project, so it is a separate daily allowance.
    """
    monkeypatch.setenv("GOOGLE_API_KEY", "key-one")
    monkeypatch.setenv("GOOGLE_API_KEY_2", "key-two")

    responses.post(
        GOOGLE_TIER_1_URL,
        status=429,
        json={"error": "daily quota exceeded for this model"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
        match=[matchers.header_matcher({"x-goog-api-key": "key-one"})],
    )
    responses.post(
        GOOGLE_TIER_1_URL,
        json=gemini_body("the other account still has quota"),
        match=[matchers.header_matcher({"x-goog-api-key": "key-two"})],
    )

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == TIER_1_KEY_2.tier
    assert result.text == "the other account still has quota"
    assert [attempt.tier for attempt in result.attempts] == [1]


def test_each_google_model_owns_its_quota_pool():
    google = [p for p in CHAIN if p.api_key_env == "GOOGLE_API_KEY"]
    pools = [p.pool for p in google]

    assert len(google) >= 2
    assert len(set(pools)) == len(pools), pools


def test_openrouter_tiers_share_one_quota_pool():
    openrouter = [p for p in CHAIN if p.api_key_env == "OPENROUTER_API_KEY"]

    assert len(openrouter) >= 2
    assert len({p.pool for p in openrouter}) == 1


def test_the_default_client_uses_the_registry_chain():
    assert LLMClient().chain is CHAIN


def test_the_time_budget_can_outlast_one_slow_call():
    """A call allowed 900s inside a 300s budget can never finish.

    Hit for real on 2026-08-17: a 64,000-token report timed out at the 180s read
    timeout. Raising one of these without the other silently guarantees failure.
    """
    _connect, read = DEFAULT_TIMEOUT

    assert DEFAULT_TOTAL_BUDGET >= read
