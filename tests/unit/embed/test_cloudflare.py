from __future__ import annotations

import json
import math

import pytest
import responses

from labpilot.embed.cloudflare import CloudflareEmbedder
from labpilot.embed.errors import EmbeddingError

ACCOUNT = "acct-123"
BASE = "https://provider.test/client/v4/accounts"
URL = f"{BASE}/{ACCOUNT}/ai/run/@cf/test-embed"

EMBEDDER = CloudflareEmbedder(name="Test BGE", url=BASE, model="@cf/test-embed", dim=3)


def reply(vectors, *, success=True, rows=None, prompt_tokens=9):
    return {
        "success": success,
        "errors": [] if success else [{"code": 7000, "message": "no route"}],
        "messages": [],
        "result": {
            "shape": [len(vectors) if rows is None else rows, 3],
            "data": [list(vector) for vector in vectors],
            "pooling": "mean",
            "usage": {"prompt_tokens": prompt_tokens, "total_tokens": prompt_tokens},
        },
    }


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)


@responses.activate
def test_the_account_id_goes_in_the_url_path_and_the_texts_go_in_text():
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0, 0.0]]), status=200)

    EMBEDDER.embed(["hello"])

    request = responses.calls[0].request
    assert request.url == URL
    assert request.headers["Authorization"] == "Bearer test-key"
    assert json.loads(request.body) == {"text": ["hello"]}


@responses.activate
def test_vectors_are_matched_by_position_because_there_is_no_index_field():
    responses.add(
        responses.POST,
        URL,
        json=reply([[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 5.0]]),
        status=200,
    )

    batch = EMBEDDER.embed(["first", "second", "third"])

    assert batch.vectors == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


@responses.activate
def test_a_vector_is_normalized_to_unit_length():
    responses.add(responses.POST, URL, json=reply([[3.0, 4.0, 0.0]]), status=200)

    (vector,) = EMBEDDER.embed(["hello"]).vectors

    assert vector == pytest.approx((0.6, 0.8, 0.0))
    assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)


@responses.activate
def test_the_reported_shape_must_agree_with_the_data_that_arrived():
    responses.add(
        responses.POST,
        URL,
        json=reply([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], rows=3),
        status=200,
    )

    with pytest.raises(EmbeddingError, match="shape says 3"):
        EMBEDDER.embed(["one", "two"])


@responses.activate
def test_a_two_hundred_that_reports_failure_is_still_an_error():
    responses.add(
        responses.POST, URL, json=reply([[1.0, 0.0, 0.0]], success=False), status=200
    )

    with pytest.raises(EmbeddingError, match="reports failure"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_usage_is_read_from_inside_the_result_envelope():
    responses.add(
        responses.POST, URL, json=reply([[1.0, 0.0, 0.0]], prompt_tokens=42), status=200
    )

    assert EMBEDDER.embed(["hello"]).prompt_tokens == 42


@responses.activate
def test_a_vector_of_the_wrong_width_is_an_error():
    responses.add(responses.POST, URL, json=reply([[1.0, 0.0]]), status=200)

    with pytest.raises(EmbeddingError, match="3 dimensions"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_an_unexpected_response_shape_is_an_error():
    responses.add(responses.POST, URL, json={"success": True}, status=200)

    with pytest.raises(EmbeddingError, match="unexpected response shape"):
        EMBEDDER.embed(["hello"])


@responses.activate
def test_a_non_200_reports_the_status_and_the_providers_own_words():
    responses.add(responses.POST, URL, json={"errors": ["nope"]}, status=403)

    with pytest.raises(EmbeddingError, match="HTTP 403"):
        EMBEDDER.embed(["hello"])


def test_a_missing_account_id_is_an_error_and_costs_no_request(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    with pytest.raises(EmbeddingError, match="CLOUDFLARE_ACCOUNT_ID is not set"):
        EMBEDDER.embed(["hello"])


def test_a_text_over_the_input_limit_is_refused_before_any_request():
    limited = CloudflareEmbedder(
        name="Test BGE", url=BASE, model="@cf/test-embed", dim=3, max_input_tokens=10
    )

    with pytest.raises(EmbeddingError, match="token input limit"):
        limited.embed(["x" * 600])
