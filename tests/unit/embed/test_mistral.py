from __future__ import annotations

import json
import math

import pytest
import requests
import responses

from labpilot.embed.defaults import MAX_BATCH_SIZE
from labpilot.embed.errors import EmbeddingError
from labpilot.embed.mistral import MistralEmbedder

URL = "https://provider.test/v1/embeddings"
EMBEDDER = MistralEmbedder(name="Test Embed", url=URL, model="test-embed", dim=3)


def reply(items, *, prompt_tokens=7):
    return {
        "id": "emb-1",
        "object": "list",
        "model": "test-embed",
        "data": [
            {"object": "embedding", "index": index, "embedding": list(vector)}
            for index, vector in items
        ],
        "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens},
    }


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")


@responses.activate
def test_the_request_carries_the_model_the_texts_and_the_bearer_key():
    responses.add(responses.POST, URL, json=reply([(0, [1.0, 0.0, 0.0])]), status=200)

    EMBEDDER.embed(["hello"])

    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert json.loads(request.body) == {"model": "test-embed", "input": ["hello"]}


@responses.activate
def test_vectors_follow_input_order_even_when_the_api_returns_them_shuffled():
    responses.add(
        responses.POST,
        URL,
        json=reply([(2, [0.0, 0.0, 5.0]), (0, [5.0, 0.0, 0.0]), (1, [0.0, 5.0, 0.0])]),
        status=200,
    )

    batch = EMBEDDER.embed(["first", "second", "third"])

    assert batch.vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@responses.activate
def test_a_vector_is_normalized_to_unit_length():
    responses.add(responses.POST, URL, json=reply([(0, [3.0, 4.0, 0.0])]), status=200)

    (vector,) = EMBEDDER.embed(["hello"]).vectors

    assert vector == pytest.approx((0.6, 0.8, 0.0))
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)


@responses.activate
def test_the_usage_and_served_model_are_reported():
    responses.add(
        responses.POST, URL, json=reply([(0, [1.0, 0.0, 0.0])], prompt_tokens=42)
    )

    batch = EMBEDDER.embed(["hello"])

    assert batch.prompt_tokens == 42
    assert batch.model == "test-embed"
    assert batch.dim == 3


@responses.activate
def test_a_zero_vector_is_an_error_because_it_cannot_be_normalized():
    responses.add(responses.POST, URL, json=reply([(0, [0.0, 0.0, 0.0])]), status=200)

    with pytest.raises(EmbeddingError, match="zero vector"):
        EMBEDDER.embed(["only stopwords"])


@responses.activate
def test_a_short_batch_is_an_error_because_vectors_would_shift_onto_wrong_texts():
    responses.add(responses.POST, URL, json=reply([(0, [1.0, 0.0, 0.0])]), status=200)

    with pytest.raises(EmbeddingError, match="asked for 2"):
        EMBEDDER.embed(["one", "two"])


@responses.activate
def test_a_vector_of_the_wrong_width_is_an_error():
    responses.add(responses.POST, URL, json=reply([(0, [1.0, 0.0])]), status=200)

    with pytest.raises(EmbeddingError, match="3 dimensions"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_a_non_200_reports_the_status_and_the_providers_own_words():
    responses.add(responses.POST, URL, json={"message": "extra_forbidden"}, status=422)

    with pytest.raises(EmbeddingError, match="HTTP 422"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_a_body_that_is_not_json_is_an_error():
    responses.add(responses.POST, URL, body="<html>gateway</html>", status=200)

    with pytest.raises(EmbeddingError, match="not JSON"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_an_unexpected_response_shape_is_an_error():
    responses.add(responses.POST, URL, json={"object": "list"}, status=200)

    with pytest.raises(EmbeddingError, match="unexpected response shape"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_a_transport_failure_is_an_error():
    responses.add(responses.POST, URL, body=requests.exceptions.ConnectionError("boom"))

    with pytest.raises(EmbeddingError, match="request failed"):
        EMBEDDER.embed(["hello"])


def test_a_missing_key_is_an_error_and_costs_no_request(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with pytest.raises(EmbeddingError, match="MISTRAL_API_KEY is not set"):
        EMBEDDER.embed(["hello"])


@pytest.mark.parametrize(
    "texts, reason",
    [
        ([], "must not be empty"),
        (["good", "   "], "must not be blank"),
        (["", "good"], "must not be blank"),
    ],
)
def test_a_caller_bug_raises_value_error_not_embedding_error(texts, reason):
    with pytest.raises(ValueError, match=reason):
        EMBEDDER.embed(texts)


def test_more_texts_than_the_batch_limit_is_a_caller_bug():
    assert MAX_BATCH_SIZE < 97  # premise: fails loudly if the cap is ever raised

    with pytest.raises(ValueError, match="batch limit"):
        EMBEDDER.embed(["x"] * 97)


@responses.activate
def test_a_batch_exactly_at_the_limit_is_accepted():
    responses.add(
        responses.POST,
        URL,
        json=reply([(i, [1.0, 0.0, 0.0]) for i in range(MAX_BATCH_SIZE)]),
        status=200,
    )

    batch = EMBEDDER.embed(["x"] * MAX_BATCH_SIZE)

    assert len(batch.vectors) == MAX_BATCH_SIZE
