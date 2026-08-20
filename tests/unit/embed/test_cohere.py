from __future__ import annotations

import json
import math

import pytest
import responses

from labpilot.embed.cohere import CohereEmbedder
from labpilot.embed.errors import EmbeddingError

URL = "https://provider.test/v2/embed"
EMBEDDER = CohereEmbedder(name="Test Cohere", url=URL, model="embed-test", dim=3)


def reply(vectors, *, input_tokens=10):
    return {
        "id": "emb-1",
        "response_type": "embeddings_by_type",
        "embeddings": {"float": [list(vector) for vector in vectors]},
        "texts": [],
        "meta": {
            "api_version": {"version": "2"},
            "billed_units": {"input_tokens": input_tokens, "image_tokens": 0},
        },
    }


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test-key")


@responses.activate
def test_a_document_batch_asks_for_search_document():
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0, 0.0]]), status=200)

    EMBEDDER.embed(["hello"])

    assert json.loads(responses.calls[0].request.body) == {
        "model": "embed-test",
        "texts": ["hello"],
        "input_type": "search_document",
        "embedding_types": ["float"],
    }


@responses.activate
def test_a_query_batch_asks_for_search_query():
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0, 0.0]]), status=200)

    EMBEDDER.embed(["hello"], task="query")

    assert json.loads(responses.calls[0].request.body)["input_type"] == "search_query"


@responses.activate
def test_vectors_are_read_from_the_float_bucket_in_order():
    responses.add(
        responses.POST,
        URL,
        json=reply([[5.0, 0.0, 0.0], [0.0, 5.0, 0.0]]),
        status=200,
    )

    batch = EMBEDDER.embed(["first", "second"])

    assert batch.vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))


@responses.activate
def test_a_vector_is_normalized_to_unit_length():
    responses.add(responses.POST, URL, json=reply([[3.0, 4.0, 0.0]]), status=200)

    (vector,) = EMBEDDER.embed(["hello"]).vectors

    assert vector == pytest.approx((0.6, 0.8, 0.0))
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)


@responses.activate
def test_billed_input_tokens_are_reported():
    responses.add(
        responses.POST, URL, json=reply([[1.0, 0.0, 0.0]], input_tokens=77), status=200
    )

    assert EMBEDDER.embed(["hello"]).prompt_tokens == 77


@responses.activate
def test_an_unexpected_response_shape_is_an_error():
    responses.add(responses.POST, URL, json={"embeddings": {}}, status=200)

    with pytest.raises(EmbeddingError, match="unexpected response shape"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_a_non_200_reports_the_status_and_the_providers_own_words():
    responses.add(responses.POST, URL, json={"message": "no api key"}, status=401)

    with pytest.raises(EmbeddingError, match="HTTP 401"):
        EMBEDDER.embed(["hello"])


def test_a_missing_key_is_an_error_and_costs_no_request(monkeypatch):
    monkeypatch.delenv("COHERE_API_KEY", raising=False)

    with pytest.raises(EmbeddingError, match="COHERE_API_KEY is not set"):
        EMBEDDER.embed(["hello"])
