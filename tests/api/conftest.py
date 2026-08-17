from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from labpilot.api import ApiConfig, app, get_client
from labpilot.llm import LLMResult

SAMPLES = Path("data/samples/quora_siamese")
COMPARE = f"{ApiConfig.PREFIX}/compare"
QUESTION = "Compare these and explain why the results diverge."

PAPER = ("a.md", b"# Method\n\nWe add two numbers.\n", "text/markdown")
CODE = ("b.py", b"def add(x, y):\n    return x + y\n", "text/x-python")

ANSWER = 'B adds two numbers [B-0 "return x + y"].'


@dataclass
class FakeClient:
    result: LLMResult
    error: Exception | None = None
    prompts: list[str] = field(default_factory=list)

    def generate(self, prompt: str, *, max_tokens: int = 0) -> LLMResult:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error

        return self.result


@pytest.fixture
def fake():
    return FakeClient(
        result=LLMResult(text=ANSWER, model="fake-model", tier=1, finish_reason="STOP")
    )


@pytest.fixture
def provider_key(monkeypatch):
    """Lifespan refuses to start with no usable tier, which is the point of it.

    A dummy value is enough: every API test replaces the client, so no request
    ever reaches a provider.
    """
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")


@pytest.fixture
def client(fake, provider_key):
    app.dependency_overrides[get_client] = lambda: fake
    # `with` runs the lifespan, so app.state is populated exactly as it is
    # under uvicorn. A bare TestClient(app) would skip it.
    with TestClient(app) as running:
        yield running
    app.dependency_overrides.clear()


@pytest.fixture
def lenient_client(fake, provider_key):
    """TestClient re-raises server exceptions by default, so the 500 handler
    never runs and cannot be observed. Only this client sees what a real
    browser would see."""
    app.dependency_overrides[get_client] = lambda: fake
    with TestClient(app, raise_server_exceptions=False) as running:
        yield running
    app.dependency_overrides.clear()


def post(client, *, a=PAPER, b=CODE, question=QUESTION):
    return client.post(COMPARE, files={"a": a, "b": b}, data={"question": question})


def problem(response) -> dict:
    return response.json()["error"]
