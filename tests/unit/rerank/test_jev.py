"""Jev returns probabilities, not an order - so WE do the sorting.

Every other tier in this package is handed a ranking by the provider. Jev is
handed a `noul` per document and this adapter turns that into an order, which
means the one thing a reranker exists to do is OUR code here rather than
theirs. Mutation testing found that gap: reversing the sort - best document
last - broke nothing in 777 tests.
"""

from __future__ import annotations

import json

import pytest
import responses

from labpilot.rerank.errors import RerankError
from labpilot.rerank.jev import JevReranker

URL = "https://provider.test/api/alpha/decisions"
RERANKER = JevReranker(name="Test Jev", url=URL, model="typesafe/jev-test")


def reply(nouls: dict[str, float], *, tokens: int = 100, cost: float = 0.0001):
    return {
        "model": "typesafe/jev-test-20260917",
        "answers": {
            key: {"type": "noul", "noul": value} for key, value in nouls.items()
        },
        "usage": {"input_tokens": tokens, "output_tokens": 10, "cost": cost},
    }


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@responses.activate
def test_the_most_probable_document_is_ranked_first():
    """The whole job. A reranker that sorts the wrong way is worse than none,
    and it cannot be noticed downstream: the caller receives a well-formed
    Ranking and cites the least relevant chunk with full confidence."""
    responses.post(URL, json=reply({"d0": 0.02, "d1": 0.97, "d2": 0.41}))

    ranking = RERANKER.rank("what is the learning rate", ["no", "yes", "maybe"])

    assert ranking.order == (1, 2, 0)
    assert ranking.scores == (0.97, 0.41, 0.02)


@responses.activate
def test_the_answer_key_dN_is_the_position_of_document_N():
    """THE TWO NUMBER SPACES, one layer earlier than usual.

    `d7` is a key we invented to carry a POSITION through a JSON object that
    has no order. If the parse ever drifted - reading the dict's insertion
    order, say - the ranking would still be well-formed and would name the
    wrong chunks. The reply below is deliberately shuffled, and the scores
    deliberately decrease with position, so insertion order and true order
    disagree.
    """
    responses.post(URL, json=reply({"d2": 0.10, "d0": 0.90, "d1": 0.50}))

    ranking = RERANKER.rank("q", ["first", "second", "third"])

    assert ranking.order == (0, 1, 2)
    assert ranking.scores == (0.90, 0.50, 0.10)


@responses.activate
def test_every_document_gets_its_own_noul_and_the_query_is_named_state():
    """The request shape, which no test downstream can see.

    Jev takes `state` plus `questions`, not `query` plus `documents`. If the
    instructions stopped referring to the document by its key, the model would
    be asked the same question N times about the whole state - and would
    answer, plausibly, N times.
    """
    responses.post(URL, json=reply({"d0": 0.5, "d1": 0.5}))

    RERANKER.rank("how is retry handled", ["alpha", "beta"])

    sent = json.loads(responses.calls[0].request.body)
    assert sent["state"] == {
        "question": "how is retry handled",
        "d0": "alpha",
        "d1": "beta",
    }
    assert set(sent["questions"]) == {"d0", "d1"}
    for key, question in sent["questions"].items():
        assert question["type"] == "noul"
        assert f"`{key}`" in question["instructions"]


@responses.activate
def test_top_n_is_applied_here_because_jev_has_no_such_parameter():
    """Every other tier sends top_n and lets the provider truncate. Jev has no
    such field, so the contract is kept identical by cutting the result - a
    caller must not have to know which tier answered."""
    responses.post(URL, json=reply({"d0": 0.1, "d1": 0.9, "d2": 0.5}))

    ranking = RERANKER.rank("q", ["a", "b", "c"], top_n=2)

    assert ranking.order == (1, 2)
    assert ranking.scores == (0.9, 0.5)


def test_more_documents_than_the_window_is_refused_before_the_request():
    """32,000 tokens on the OpenRouter route. 50 Go chunks are already ~23,700,
    so the ceiling is real and a refusal here costs nothing - unlike one that
    spends a request to learn the same thing."""
    with pytest.raises(ValueError, match="over Test Jev's limit of 50"):
        RERANKER.rank("q", ["doc"] * 51)


@responses.activate
def test_a_missing_noul_is_our_error_and_not_a_crash():
    responses.post(URL, json={"model": "x", "answers": {"d0": {"type": "choice"}}})

    with pytest.raises(RerankError, match="unexpected response shape"):
        RERANKER.rank("q", ["a"])
