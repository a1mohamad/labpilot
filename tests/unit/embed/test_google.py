from __future__ import annotations

import json

import pytest
import responses

from labpilot.embed.errors import EmbeddingError
from labpilot.embed.google import GoogleEmbedder

BASE = "https://provider.test/v1beta/models"
URL = f"{BASE}/test-embed:batchEmbedContents"
EMBEDDER = GoogleEmbedder(name="Test Gemini", url=BASE, model="test-embed", dim=3)


def reply(vectors):
    return {"embeddings": [{"values": list(vector)} for vector in vectors]}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")


@responses.activate
def test_the_model_lives_in_the_url_and_the_key_in_its_own_header():
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0, 0.0]]), status=200)

    EMBEDDER.embed(["hello"])

    request = responses.calls[0].request
    assert request.url == URL
    assert request.headers["x-goog-api-key"] == "test-key"
    assert "Authorization" not in request.headers


@responses.activate
def test_every_text_gets_its_own_request_object():
    # Passing several inputs to ONE request returns a single aggregated vector.
    responses.add(
        responses.POST, URL, json=reply([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), status=200
    )

    EMBEDDER.embed(["first", "second"])

    sent = json.loads(responses.calls[0].request.body)["requests"]
    assert len(sent) == 2
    assert [item["content"]["parts"][0]["text"] for item in sent] == [
        "first",
        "second",
    ]
    assert {item["model"] for item in sent} == {"models/test-embed"}


@responses.activate
@pytest.mark.parametrize(
    "task, expected",
    [("document", "RETRIEVAL_DOCUMENT"), ("query", "RETRIEVAL_QUERY")],
)
def test_the_task_becomes_googles_own_task_type(task, expected):
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0, 0.0]]), status=200)

    EMBEDDER.embed(["hello"], task=task)

    sent = json.loads(responses.calls[0].request.body)["requests"]
    assert sent[0]["taskType"] == expected


@responses.activate
def test_vectors_are_read_from_values_in_order():
    responses.add(
        responses.POST,
        URL,
        json=reply([[5.0, 0.0, 0.0], [0.0, 5.0, 0.0]]),
        status=200,
    )

    batch = EMBEDDER.embed(["first", "second"])

    assert batch.vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


@responses.activate
def test_usage_is_reported_as_zero_because_the_batch_endpoint_sends_none():
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0, 0.0]]), status=200)

    assert EMBEDDER.embed(["hello"]).prompt_tokens == 0


@responses.activate
def test_a_blocked_location_reports_googles_own_words():
    responses.add(
        responses.POST,
        URL,
        json={
            "error": {
                "code": 400,
                "message": "User location is not supported for the API use.",
                "status": "FAILED_PRECONDITION",
            }
        },
        status=400,
    )

    with pytest.raises(EmbeddingError, match="User location is not supported"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_an_unexpected_response_shape_is_an_error():
    responses.add(responses.POST, URL, json={"embeddings": [{}]}, status=200)

    with pytest.raises(EmbeddingError, match="unexpected response shape"):
        EMBEDDER.embed(["hello"])


def test_a_missing_key_is_an_error_and_costs_no_request(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(EmbeddingError, match="GOOGLE_API_KEY is not set"):
        EMBEDDER.embed(["hello"])
