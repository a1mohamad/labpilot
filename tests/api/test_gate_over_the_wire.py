"""The gate through the real chain and the real provider code.

`test_gate.py` gives `make_gate` a fake client, so nothing proved that the tool
really reaches the provider in its request, that the answer is read out of a
real function call, or that a wrong verdict goes on to the NEXT tier through the
real `LLMClient` (D50). Only the provider's HTTP is replaced, by `responses`.
"""

from __future__ import annotations

import json

import pytest
import responses

from labpilot.agent import GATE_TOOL_NAME
from labpilot.api.gate import make_gate
from labpilot.llm import GeminiProvider, LLMClient

BASE = "https://provider.test/v1beta/models"


def provider(model: str, tier: int) -> GeminiProvider:
    return GeminiProvider(
        name=f"Tier {tier}",
        tier=tier,
        url=BASE,
        model=model,
        api_key_env="TEST_API_KEY",
        quota_pool=f"P{tier}",
        context_window=1_000_000,
        max_output_tokens=64_000,
    )


def url(model: str) -> str:
    return f"{BASE}/{model}:generateContent"


def called(arguments: dict, model: str) -> dict:
    return {
        "modelVersion": model,
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": GATE_TOOL_NAME, "args": arguments}}
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", lambda _seconds: None)


@responses.activate
def test_the_tool_reaches_the_provider_and_the_verdict_is_read_from_the_call():
    responses.post(
        url("one"),
        json=called({"verdict": "FULL", "reason": "a paper and its code"}, "one"),
    )
    gate = make_gate(LLMClient(chain=(provider("one", 1),)))

    found = gate("a paper about routing", "code that routes")

    assert found.verdict == "FULL"
    assert found.reason == "a paper and its code"
    sent = json.loads(responses.calls[0].request.body)
    [declared] = sent["tools"][0]["functionDeclarations"]
    assert declared["name"] == GATE_TOOL_NAME
    text = sent["contents"][0]["parts"][0]["text"]
    assert "a paper about routing" in text and "code that routes" in text


@responses.activate
def test_a_verdict_that_is_not_one_of_the_three_goes_on_to_the_next_tier():
    responses.post(url("one"), json=called({"verdict": "MAYBE", "reason": "?"}, "one"))
    responses.post(
        url("two"),
        json=called({"verdict": "NONE", "reason": "different things"}, "two"),
    )
    gate = make_gate(LLMClient(chain=(provider("one", 1), provider("two", 2))))

    found = gate("summary of A", "summary of B")

    assert found.verdict == "NONE"
    assert [call.request.url for call in responses.calls] == [url("one"), url("two")]
