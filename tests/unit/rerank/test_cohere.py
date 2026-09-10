from __future__ import annotations

import json

import pytest
import responses

from labpilot.rerank.cohere import CohereReranker
from labpilot.rerank.errors import RerankError

URL = "https://provider.test/v2/rerank"
RERANKER = CohereReranker(name="Test Cohere", url=URL, model="rerank-test")


def reply(hits, *, search_units=1):
    return {
        "id": "abc",
        "results": [
            {"index": index, "relevance_score": score} for index, score in hits
        ],
        "meta": {
            "api_version": {"version": "2"},
            "billed_units": {"search_units": search_units},
        },
    }


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv("COHERE_API_KEY", "test-key")


@responses.activate
def test_the_model_goes_in_the_body_and_documents_are_plain_strings():
    responses.add(responses.POST, URL, json=reply([(1, 0.9), (0, 0.1)]), status=200)

    RERANKER.rank("why", ["first", "second"])

    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert json.loads(request.body) == {
        "model": "rerank-test",
        "query": "why",
        "documents": ["first", "second"],
    }


@responses.activate
def test_top_n_is_sent_as_top_n_only_when_it_is_asked_for():
    responses.add(responses.POST, URL, json=reply([(1, 0.9)]), status=200)

    RERANKER.rank("why", ["first", "second"], top_n=1)

    assert json.loads(responses.calls[0].request.body)["top_n"] == 1


@responses.activate
def test_the_order_is_read_from_index_and_the_scores_from_relevance_score():
    responses.add(
        responses.POST, URL, json=reply([(2, 0.84), (0, 0.25), (1, 0.24)]), status=200
    )

    ranking = RERANKER.rank("why", ["a", "b", "c"])

    assert ranking.order == (2, 0, 1)
    assert ranking.scores == (0.84, 0.25, 0.24)
    assert ranking.model == "rerank-test"


@responses.activate
def test_an_unexpected_response_shape_is_an_error():
    responses.add(responses.POST, URL, json={"results": [{"index": 0}]}, status=200)

    with pytest.raises(RerankError, match="unexpected response shape"):
        RERANKER.rank("why", ["a"])


@responses.activate
def test_a_non_200_reports_the_status_and_the_providers_own_words():
    responses.add(responses.POST, URL, json={"message": "no documents"}, status=400)

    with pytest.raises(RerankError, match="HTTP 400"):
        RERANKER.rank("why", ["a"])


# The integrity guards below live in the shared template, so they are tested
# ONCE through one real door rather than parametrized over all three. Running
# one assertion three times over the same code path is the fake-parametrized
# trap - test_every_reranker already proves each provider inherits the
# template, which is the part that genuinely differs.


@responses.activate
def test_a_ranking_that_names_a_document_we_never_sent_is_refused():
    """The worst failure this layer has, because nothing else would notice.

    The position is how the caller looks a chunk back up, so an index off by
    one cites the wrong file and the wrong line - with full confidence, and
    with a quote that still resolves.
    """
    responses.add(responses.POST, URL, json=reply([(0, 0.9), (7, 0.8)]), status=200)

    with pytest.raises(RerankError, match="never sent"):
        RERANKER.rank("why", ["a", "b"])


@responses.activate
def test_a_ranking_that_names_the_same_document_twice_is_refused():
    responses.add(responses.POST, URL, json=reply([(1, 0.9), (1, 0.8)]), status=200)

    with pytest.raises(RerankError, match="ranked twice"):
        RERANKER.rank("why", ["a", "b"])


@responses.activate
def test_more_results_than_documents_is_refused():
    responses.add(
        responses.POST, URL, json=reply([(0, 0.9), (1, 0.8), (0, 0.7)]), status=200
    )

    with pytest.raises(RerankError, match="sent 2 documents but got 3"):
        RERANKER.rank("why", ["a", "b"])


@responses.activate
def test_fewer_results_than_documents_is_legal_because_that_is_what_top_n_is():
    responses.add(responses.POST, URL, json=reply([(2, 0.9)]), status=200)

    ranking = RERANKER.rank("why", ["a", "b", "c"], top_n=1)

    assert ranking.order == (2,)


@responses.activate
def test_a_document_over_the_token_cap_is_refused_before_any_request():
    """Cohere splits a document past ~510 tokens and bills each piece, so this
    failure is a BILL rather than an exception - no provider reports it."""
    responses.add(responses.POST, URL, json=reply([(0, 0.9)]), status=200)

    with pytest.raises(RerankError, match="would be split and billed"):
        RERANKER.rank("why", ["x" * 2_000])

    assert len(responses.calls) == 0
