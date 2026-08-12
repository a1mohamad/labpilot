from __future__ import annotations

import time

import pytest
import responses

import labpilot.llm as llm
from labpilot.llm import CHAIN, LLMClient

GEMINI_3_6_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/gemini-3.6-flash:generateContent"
)
GEMINI_3_5_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/gemini-3.5-flash:generateContent"
)
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@pytest.fixture
def keys(monkeypatch):
    for name in ("GOOGLE_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(name, "secret-key")


def gemini_body(text="from gemini"):
    return {
        "modelVersion": "gemini-3.6-flash",
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
    responses.post(GEMINI_3_6_URL, json=gemini_body())

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == 1
    assert result.text == "from gemini"
    assert result.attempts == ()


@responses.activate
def test_the_real_chain_skips_the_second_google_tier_when_google_is_spent(keys):
    responses.post(
        GEMINI_3_6_URL,
        status=429,
        json={"error": "daily quota exceeded"},
        headers={"X-RateLimit-Reset": str(int(time.time() + 3600))},
    )
    responses.post(MISTRAL_URL, status=500, json={"error": "upstream failure"})
    responses.post(GEMINI_3_5_URL, json=gemini_body("tier 3 should never run"))
    responses.post(OPENROUTER_URL, json=openai_body("nvidia/nemotron-3-ultra"))

    result = LLMClient().generate("why do these diverge?")

    assert result.tier == 4
    assert [attempt.tier for attempt in result.attempts] == [1, 2, 3]
    assert "exhausted" in result.attempts[2].error
    assert GEMINI_3_5_URL not in [call.request.url for call in responses.calls]


def test_the_default_client_uses_the_registry_chain():
    assert LLMClient().chain is CHAIN
