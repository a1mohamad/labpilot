from __future__ import annotations

import time

import pytest
import responses

import labpilot.llm as llm
from labpilot.llm import CHAIN, LLMClient

GOOGLE_TIER_1_URL = f"{CHAIN[0].url}/{CHAIN[0].model}:generateContent"
GOOGLE_TIER_2_URL = f"{CHAIN[1].url}/{CHAIN[1].model}:generateContent"
GOOGLE_TIER_3_URL = f"{CHAIN[2].url}/{CHAIN[2].model}:generateContent"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture
def keys(monkeypatch):
    for name in ("GOOGLE_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(name, "secret-key")


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
    responses.post(
        GOOGLE_TIER_1_URL,
        status=429,
        json={"error": "daily quota exceeded for this model"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
    )
    responses.post(GOOGLE_TIER_2_URL, json=gemini_body("tier 2 still has quota"))

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == 2
    assert result.text == "tier 2 still has quota"
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
