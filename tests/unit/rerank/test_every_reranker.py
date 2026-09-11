from __future__ import annotations

import pytest

from labpilot.ingest.defaults import MAX_CHUNK_TOKENS
from labpilot.rerank import LLM_RERANK_ORDER, RERANK_CHAIN
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


# Measured on quora at a 30-document window, against vector alone's MRR 0.608.
# A model that scores BELOW that line makes retrieval worse by being in the
# chain at all, because the chain already ends in skip().
MEASURED_MRR = {
    "gemini-3.5-flash-lite": 0.799,
    "gemini-3.1-flash-lite": 0.745,
    "gemma-4-26b-a4b-it": 0.732,
    "gemma-4-31b-it": 0.732,
    "rerank-3-lite": 0.725,
    "rerank-v4.0-fast": 0.669,
    "@cf/baai/bge-reranker-base": 0.520,
}
VECTOR_ALONE = 0.608

# Deliberate and arguable: bge-reranker-base measured BELOW vector alone and is
# kept as the last tier anyway, on one corpus and one saturated fixture, because
# it is the only tier whose budget cannot run out. Slice 8 re-measures it; if
# the number holds, the right move is to DELETE the tier, not reorder it.
KNOWN_WORSE_THAN_NOT_RERANKING = ("@cf/baai/bge-reranker-base",)


def test_the_chain_is_ordered_by_measured_quality():
    """The order used to be a quota-shape argument. It is evidence now, and a
    reorder that contradicts the measurements should fail the build."""
    scored = [
        (r.model, MEASURED_MRR[r.model])
        for r in RERANK_CHAIN
        if r.model in MEASURED_MRR
    ]
    ranked = [model for model, _ in scored]

    assert ranked == [model for model, _ in sorted(scored, key=lambda kv: -kv[1])], (
        f"chain order {ranked} disagrees with the measured MRR"
    )


def test_only_a_named_tier_may_be_worse_than_not_reranking_at_all():
    """Pin the exceptions by name - the OUTPUT_TOO_SMALL pattern.

    A tier below vector alone actively costs quality when reached, and the
    chain already ends in skip(), so adding another one silently is a real
    regression rather than a weaker fallback.
    """
    harmful = [
        r.model
        for r in RERANK_CHAIN
        if MEASURED_MRR.get(r.model, 1.0) < VECTOR_ALONE
        and r.model not in KNOWN_WORSE_THAN_NOT_RERANKING
    ]

    assert not harmful, (
        f"{harmful} measured WORSE than not reranking, so being in the chain "
        f"makes retrieval worse. The chain already ends in skip(): drop the "
        f"tier, or name it in KNOWN_WORSE_THAN_NOT_RERANKING with the reason."
    )


def test_the_llm_tiers_are_recorded_in_measured_order_too():
    """They cannot be IN the chain - they need llm/, and an adapter may not
    import another adapter - so the order is data that slice 7 assembles."""
    scores = [MEASURED_MRR[model] for model in LLM_RERANK_ORDER]

    assert scores == sorted(scores, reverse=True), LLM_RERANK_ORDER
    assert all(score > VECTOR_ALONE for score in scores)
