from __future__ import annotations

import json

import pytest
import responses

from labpilot.rerank.voyage import VoyageReranker

URL = "https://provider.test/v1/rerank"
RERANKER = VoyageReranker(name="Test Voyage", url=URL, model="rerank-test")


def reply(hits, *, total_tokens=48):
    return {
        "object": "list",
        "data": [{"relevance_score": score, "index": index} for index, score in hits],
        "model": "rerank-test",
        "usage": {"total_tokens": total_tokens},
    }


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")


@responses.activate
def test_the_results_live_under_data_not_results():
    responses.add(responses.POST, URL, json=reply([(1, 0.78), (0, 0.37)]), status=200)

    ranking = RERANKER.rank("why", ["first", "second"])

    assert ranking.order == (1, 0)
    assert ranking.scores == (0.78, 0.37)


@responses.activate
def test_top_n_is_sent_as_top_k_because_voyage_spells_it_differently():
    responses.add(responses.POST, URL, json=reply([(1, 0.78)]), status=200)

    RERANKER.rank("why", ["first", "second"], top_n=1)

    body = json.loads(responses.calls[0].request.body)
    assert body["top_k"] == 1
    assert "top_n" not in body


def test_voyage_is_capped_at_the_width_a_card_free_account_can_actually_serve():
    """1,000 is Voyage's PUBLISHED limit and the wrong number twice over.

    That is the billed tier's DOCUMENT limit, and what binds a card-free
    account is TOKENS: 10,000 a minute, counting a call whole. Measured
    2026-09-11 on our own chunks, each after a clean 90-second wait -
    50 documents refused, 40 refused, 30 passed.

    So the honest ceiling is 30, and declaring it is what lets the ask path
    send its full window to tiers that can take it while Voyage still ANSWERS
    instead of burning one of its 3 requests a minute on a refusal.
    """
    assert RERANKER.max_documents == 30
