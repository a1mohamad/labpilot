from __future__ import annotations

import json

import pytest
import responses

from labpilot.rerank.cloudflare import CloudflareReranker
from labpilot.rerank.errors import RerankError

ACCOUNT = "acct-123"
BASE = "https://provider.test/client/v4/accounts"
URL = f"{BASE}/{ACCOUNT}/ai/run/@cf/test-rerank"

RERANKER = CloudflareReranker(name="Test BGE Rerank", url=BASE, model="@cf/test-rerank")


def reply(hits, *, success=True, neurons=0.0246):
    return {
        "success": success,
        "errors": [] if success else [{"code": 3043, "message": "AiError"}],
        "messages": [],
        "result": {
            "response": [{"id": index, "score": score} for index, score in hits],
            "usage": {
                "prompt_tokens": 87,
                "total_tokens": 87,
                "neurons": neurons,
            },
        },
    }


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_KEY", "test-key")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", ACCOUNT)


@responses.activate
def test_the_account_goes_in_the_url_and_documents_are_wrapped_as_contexts():
    responses.add(responses.POST, URL, json=reply([(1, 0.98), (0, 0.01)]), status=200)

    RERANKER.rank("why", ["first", "second"])

    request = responses.calls[0].request
    assert request.url == URL
    assert json.loads(request.body) == {
        "query": "why",
        "contexts": [{"text": "first"}, {"text": "second"}],
    }


@responses.activate
def test_the_position_is_read_from_id_because_cloudflare_does_not_say_index():
    responses.add(responses.POST, URL, json=reply([(1, 0.98), (0, 0.01)]), status=200)

    ranking = RERANKER.rank("why", ["first", "second"])

    assert ranking.order == (1, 0)
    assert ranking.scores == (0.98, 0.01)


@responses.activate
def test_a_two_hundred_that_reports_failure_is_still_an_error():
    """Measured live: empty contexts answers HTTP 500, but Cloudflare also
    reports real failures inside a 200 - so the status code is not enough."""
    responses.add(
        responses.POST, URL, json=reply([(0, 0.5)], success=False), status=200
    )

    with pytest.raises(RerankError, match="reports failure"):
        RERANKER.rank("why", ["first"])


def test_a_missing_account_id_is_an_error_and_costs_no_request(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    with pytest.raises(RerankError, match="CLOUDFLARE_ACCOUNT_ID is not set"):
        RERANKER.rank("why", ["first"])
