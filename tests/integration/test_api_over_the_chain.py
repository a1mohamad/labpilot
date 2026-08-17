"""API -> pipeline -> LLMClient -> chain -> provider HTTP, all real but the last hop.

The api/ tests replace LLMClient with a fake, so the chain never runs. The
llm/ tests drive the chain with FakeProviders, so HTTP never runs. Nothing
joined the two, and the five-way failure rule only matters if its verdict
survives all the way into an HTTP response body.

Mocked at the provider boundary with `responses`, so no network and no quota.
"""

from __future__ import annotations

import pytest
import responses
from fastapi.testclient import TestClient

from labpilot.api import app, get_client
from labpilot.llm import GeminiProvider, LLMClient

BASE = "https://provider.test/v1beta/models"

PAPER = ("a.md", b"# Method\n\nWe add two numbers.\n", "text/markdown")
CODE = ("b.py", b"def add(x, y):\n    return x + y\n", "text/x-python")
QUESTION = "Compare these and explain why the results diverge."


def provider(*, name: str, tier: int, model: str, pool: str) -> GeminiProvider:
    return GeminiProvider(
        name=name,
        tier=tier,
        url=BASE,
        model=model,
        api_key_env="TEST_API_KEY",
        quota_pool=pool,
        context_window=1_000_000,
        max_output_tokens=64_000,
    )


CHAIN = (
    provider(name="First", tier=1, model="first", pool="POOL_A"),
    provider(name="Second", tier=2, model="second", pool="POOL_A"),
    provider(name="Third", tier=3, model="third", pool="POOL_B"),
)


def url(model: str) -> str:
    return f"{BASE}/{model}:generateContent"


def answered(model: str, text: str = "A and B agree.") -> dict:
    """The provider reports its own model version, and that is what reaches
    LLMResult.model — not the name we gave the provider in the registry."""
    return {
        "modelVersion": model,
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", lambda _seconds: None)
    app.dependency_overrides[get_client] = lambda: LLMClient(chain=CHAIN)
    yield TestClient(app)
    app.dependency_overrides.clear()


def post(client):
    return client.post(
        "/compare",
        files={"a": PAPER, "b": CODE},
        data={"question": QUESTION},
    )


@responses.activate
def test_a_healthy_first_tier_answers_and_no_other_tier_is_called(client):
    responses.add(responses.POST, url("first"), json=answered("first-001"))

    body = post(client).json()

    assert body["answer"] == "A and B agree."
    assert body["model"] == "first-001"
    assert body["tier"] == 1
    assert body["attempts"] == []
    assert len(responses.calls) == 1


@responses.activate
def test_a_503_is_retried_on_the_same_tier_rather_than_falling_through(client):
    responses.add(responses.POST, url("first"), json={}, status=503)
    responses.add(responses.POST, url("first"), json=answered("first-001"))

    body = post(client).json()

    assert body["tier"] == 1, "503 means try again, not give up on the tier"
    assert body["attempts"] == []
    assert len(responses.calls) == 2


@responses.activate
def test_a_spent_pool_skips_its_other_tier_and_costs_no_request(client):
    responses.add(
        responses.POST,
        url("first"),
        json={},
        status=429,
        headers={"Retry-After": "86400"},
    )
    responses.add(responses.POST, url("third"), json=answered("third-001"))

    body = post(client).json()

    assert body["tier"] == 3, "tier 2 shares POOL_A and must be skipped"
    assert [one["model"] for one in body["attempts"]] == ["First", "Second"]
    assert url("second") not in [call.request.url for call in responses.calls]


@responses.activate
def test_a_prompt_larger_than_a_tier_costs_that_tier_no_request(client):
    """_check_fits runs before requests.post, so an impossible tier is free."""
    tiny = GeminiProvider(
        name="Tiny",
        tier=1,
        url=BASE,
        model="tiny",
        api_key_env="TEST_API_KEY",
        context_window=100,
        max_output_tokens=50,
    )
    app.dependency_overrides[get_client] = lambda: LLMClient(chain=(tiny, CHAIN[2]))
    responses.add(responses.POST, url("third"), json=answered("third-001"))

    body = post(client).json()

    assert body["tier"] == 3
    assert body["attempts"][0]["model"] == "Tiny"
    assert url("tiny") not in [call.request.url for call in responses.calls]


@responses.activate
def test_when_every_tier_fails_the_503_names_all_of_them(client):
    for model in ("first", "second", "third"):
        responses.add(responses.POST, url(model), json={}, status=500)

    response = post(client)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert [one["tier"] for one in detail["attempts"]] == [1, 2, 3]
    assert all("500" in one["error"] for one in detail["attempts"])


@responses.activate
def test_the_prompt_that_reaches_the_provider_carries_both_sides(client):
    responses.add(responses.POST, url("first"), json=answered("first-001"))

    post(client)

    sent = responses.calls[0].request.body.decode("utf-8")
    assert "A-0" in sent
    assert "B-0" in sent
    assert "def add(x, y):" in sent
    assert QUESTION in sent
