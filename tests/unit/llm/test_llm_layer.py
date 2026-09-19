from __future__ import annotations

import time

import pytest
import responses
from responses import matchers

from labpilot.llm import CHAIN, ClineProvider, GeminiProvider, LLMClient
from labpilot.llm.defaults import DEFAULT_TIMEOUT, DEFAULT_TOTAL_BUDGET


def url_for(provider):
    """Gemini puts the model in the PATH; everyone else posts to a fixed URL."""
    if isinstance(provider, GeminiProvider):
        return f"{provider.url}/{provider.model}:generateContent"
    return provider.url


def body_for(provider, text):
    """One answer, in whichever wire shape this provider really speaks."""
    if isinstance(provider, GeminiProvider):
        return {
            "modelVersion": provider.model,
            "candidates": [
                {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
            ],
        }

    body = {
        "model": provider.model,
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
    }

    # Cline wraps the OpenAI shape one level deeper.
    if isinstance(provider, ClineProvider):
        return {"data": body, "success": True}

    return body


TIER_1 = CHAIN[0]

# Derived by POOL, never indexed. These three tests are about GOOGLE's
# per-model quota, and they used to reach it as CHAIN[0] - which stopped being
# Google the moment a free tier was put in front of it. The comment below this
# block already said "derived, never indexed"; CHAIN[0] was an index wearing a
# derivation's clothes.
GOOGLE_1 = next(p for p in CHAIN if p.api_key_env == "GOOGLE_API_KEY")
GOOGLE_1_KEY_2 = next(
    p
    for p in CHAIN
    if p.model == GOOGLE_1.model and p.api_key_env == "GOOGLE_API_KEY_2"
)

# The first GOOGLE tier running a DIFFERENT model, so the rescue cannot come
# from the same model on the second key.
ANOTHER_MODEL = next(
    p for p in CHAIN if isinstance(p, GeminiProvider) and p.model != GOOGLE_1.model
)

# Every tier ahead of Google, whatever it is. Mocked as a plain failure so
# these tests measure Google's behaviour and nothing else.
BEFORE_GOOGLE = tuple(p for p in CHAIN if p.tier < GOOGLE_1.tier)

# Everything that is neither the spent model, its twin, nor the rescue.
#
# It used to be BEFORE_GOOGLE alone, which quietly assumed the rescue tier sat
# immediately after the twin. That held until 2026-09-19, when DeepSeek and
# two Qwen tiers were inserted between them and the test began failing for a
# reason that had nothing to do with quota pools. Deriving the scenery from
# what the test is ABOUT, rather than from a position, makes an insertion
# anywhere in the chain harmless.
SCENERY = tuple(
    p
    for p in CHAIN
    if p.tier < ANOTHER_MODEL.tier and p not in (GOOGLE_1, GOOGLE_1_KEY_2)
)

GOOGLE_TIER_1_URL = url_for(GOOGLE_1)
ANOTHER_MODEL_URL = url_for(ANOTHER_MODEL)
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def fail_everything_before_google():
    """400, NOT 500 - and that stopped being an arbitrary choice on 2026-09-19.

    These tiers are scenery: the tests below measure Google, and everything in
    front of it only has to get out of the way. A 500 used to do that in one
    call. Since 500 joined RETRYABLE_STATUSES it costs THREE calls and a real
    3s + 10s wait per tier, so both tests that call this ran for 13.01 seconds
    each - green, and slow for a reason that has nothing to do with what they
    check.

    400 is the status that still means exactly "next tier, retrying cannot
    change it", which is what the scenery is for.
    """
    for provider in SCENERY:
        responses.post(
            url_for(provider), status=400, json={"error": "not the tier under test"}
        )


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

    # Belt and braces after the 500 retry landed. The status above is now 400,
    # so nothing here waits - but a unit test must never be able to sleep for
    # real, and the next retryable status added to defaults.py should not be
    # able to put thirteen seconds back into this file unnoticed.
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", lambda _seconds: None)


@responses.activate
def test_the_real_chain_returns_tier_one_when_tier_one_answers(keys):
    """Whatever tier 1 is. It was Google, it is now Cline, and the rule that
    a healthy first tier ends the walk is the same either way."""
    responses.post(url_for(TIER_1), json=body_for(TIER_1, "from tier one"))

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == 1
    assert result.text == "from tier one"
    assert result.attempts == ()


@responses.activate
def test_one_spent_google_model_does_not_skip_the_others(keys):
    """Google bills per model, so one spent model must not retire the rest.

    Both accounts of the leading model are spent here, because they share a
    URL and differ only by key - so the rescue has to come from a genuinely
    DIFFERENT model. Collapsing the pool onto the API key would mark every
    Google tier dead on the first 429 and this would fail.
    """
    fail_everything_before_google()
    responses.post(
        GOOGLE_TIER_1_URL,
        status=429,
        json={"error": "daily quota exceeded for this model"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
    )
    responses.post(ANOTHER_MODEL_URL, json=body_for(ANOTHER_MODEL, "a different model"))

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == ANOTHER_MODEL.tier
    assert result.text == "a different model"
    # Every tier ahead of the rescue was tried, and NONE was skipped - which
    # is the whole claim: a 429 on one Google MODEL must not retire the pool
    # that the others sit on.
    assert [attempt.tier for attempt in result.attempts] == [
        p.tier for p in CHAIN if p.tier < ANOTHER_MODEL.tier
    ]


@responses.activate
def test_a_spent_model_falls_through_to_the_second_google_account(keys, monkeypatch):
    """The entire point of the second account, and nothing covered it.

    The two tiers are the SAME model on two keys, so they share a URL and can
    only be told apart by the header. Key 1 is spent; key 2 must answer - it is
    a separate project, so it is a separate daily allowance.
    """
    monkeypatch.setenv("GOOGLE_API_KEY", "key-one")
    monkeypatch.setenv("GOOGLE_API_KEY_2", "key-two")

    fail_everything_before_google()
    responses.post(
        GOOGLE_TIER_1_URL,
        status=429,
        json={"error": "daily quota exceeded for this model"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
        match=[matchers.header_matcher({"x-goog-api-key": "key-one"})],
    )
    responses.post(
        GOOGLE_TIER_1_URL,
        json=body_for(GOOGLE_1, "the other account still has quota"),
        match=[matchers.header_matcher({"x-goog-api-key": "key-two"})],
    )

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == GOOGLE_1_KEY_2.tier
    assert result.text == "the other account still has quota"
    assert [attempt.tier for attempt in result.attempts] == [
        *(p.tier for p in BEFORE_GOOGLE),
        GOOGLE_1.tier,
    ]


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
