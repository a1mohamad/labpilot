from __future__ import annotations

import time

import pytest
import responses

import labpilot.llm as llm
from labpilot.llm import CHAIN, LLMClient

GOOGLE_TIER_1_URL = f"{CHAIN[0].url}/{CHAIN[0].model}:generateContent"
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
def test_the_real_chain_skips_every_google_tier_when_google_is_spent(keys):
    responses.post(
        GOOGLE_TIER_1_URL,
        status=429,
        json={"error": "daily quota exceeded"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
    )
    responses.post(MISTRAL_URL, status=500, json={"error": "upstream failure"})
    responses.post(GOOGLE_TIER_3_URL, json=gemini_body("no google tier may run"))
    responses.post(OPENROUTER_URL, json=openai_body("nvidia/nemotron-3-ultra"))

    result = LLMClient().generate("why do these diverge?")

    google_tiers = [p.tier for p in CHAIN if p.api_key_env == "GOOGLE_API_KEY"]
    skipped = {a.tier for a in result.attempts if "exhausted" in a.error}
    winner = next(p for p in CHAIN if p.tier == result.tier)

    assert winner.api_key_env != "GOOGLE_API_KEY"
    assert skipped == set(google_tiers[1:])
    assert GOOGLE_TIER_3_URL not in [call.request.url for call in responses.calls]


def test_the_default_client_uses_the_registry_chain():
    assert LLMClient().chain is CHAIN
