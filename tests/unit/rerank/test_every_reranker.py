from __future__ import annotations

import pytest

from labpilot.ingest.defaults import MAX_CHUNK_TOKENS
from labpilot.rerank import RERANK_CHAIN
from labpilot.rerank.base import HTTPReranker
from labpilot.rerank.errors import RerankError

CASES = pytest.mark.parametrize(
    "reranker", RERANK_CHAIN, ids=lambda reranker: reranker.model
)


@CASES
def test_every_reranker_shares_the_one_http_template(reranker):
    assert isinstance(reranker, HTTPReranker)


@CASES
def test_every_reranker_rejects_a_blank_query_as_a_caller_bug(reranker):
    with pytest.raises(ValueError, match="must not be blank"):
        reranker.rank("   ", ["a document"])


@CASES
def test_every_reranker_rejects_an_empty_document_list_as_a_caller_bug(reranker):
    with pytest.raises(ValueError, match="no documents to rank"):
        reranker.rank("why", [])


@CASES
def test_every_reranker_refuses_without_credentials_and_costs_no_request(
    reranker, monkeypatch
):
    monkeypatch.delenv(reranker.api_key_env, raising=False)
    if reranker.account_env:
        monkeypatch.delenv(reranker.account_env, raising=False)

    with pytest.raises(RerankError, match="is not set"):
        reranker.rank("why", ["a document"])


@CASES
def test_every_reranker_can_take_a_document_at_our_chunk_cap(reranker):
    """A reranker whose document limit sits below our chunk cap would refuse
    every call locally - the same useless-but-loud failure the embedder guard
    caught on its first run, where 3 of 78 chunks crossed BGE's 512 limit."""
    assert reranker.max_document_tokens >= MAX_CHUNK_TOKENS


@CASES
def test_every_reranker_refuses_more_documents_than_it_accepts(reranker):
    assert reranker.max_documents <= 1_000  # premise: a literal, so a raised
    #                                         cap fails here instead of silently
    #                                         growing the payload with itself

    with pytest.raises(ValueError, match="over .* limit of"):
        reranker.rank("why", ["doc"] * 1_001)
