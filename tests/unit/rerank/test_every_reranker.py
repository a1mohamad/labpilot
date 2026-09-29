from __future__ import annotations

from pathlib import Path

import pytest
import responses

# BOUND AT IMPORT, on purpose. tests/conftest.py empties
# labpilot.api.reranking.CHAIN for every non-smoke test, but a name bound here
# still holds the real tuple - and the real tuple is the list the ask path
# reaches for, which is the one worth checking.
from labpilot.api.reranking import CHAIN as SHIPPED_CHAIN
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS
from labpilot.llm.registry import GOOGLE_KEYS
from labpilot.rerank import LLM_RERANK_ORDER, RERANK_CHAIN, LLMReranker
from labpilot.rerank.base import HTTPReranker
from labpilot.rerank.errors import RerankError

ROOT = Path(__file__).resolve().parents[3]
SMOKE_WORKFLOW = ROOT / ".github" / "workflows" / "smoke.yaml"

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

# EMPTY SINCE 2026-09-19, and that is the point: bge-reranker-base was the one
# name here, kept as the last tier although it measured BELOW vector alone,
# pending a v3 re-check. The re-check was abandoned when Gemma's quota ran out,
# so the tier was DELETED on v1's F6 instead - which had already named the
# condition and seen it met. The chain ends in skip(), which is strictly better
# than a tier that makes retrieval worse.
KNOWN_WORSE_THAN_NOT_RERANKING: tuple[str, ...] = ()

# MEASURED_MRR above is QUORA ONLY - 82 chunks, saturated, one corpus. v2's G20
# added three more and Cohere's place did not reproduce: it gains +6.0q over
# three corpora and has never hurt one, while flash-lite gains +6.1q over
# thirteen and hurts on three. So the chain orders Cohere on BREADTH and this
# table cannot see why. Named rather than deleted, the OUTPUT_TOO_SMALL
# pattern: a deliberate exception is documented, an accidental one is red.
ORDERED_ON_BREADTH_NOT_QUORA = ("rerank-v4.0-fast",)


def test_the_chain_is_ordered_by_measured_quality():
    """The order used to be a quota-shape argument. It is evidence now, and a
    reorder that contradicts the measurements should fail the build."""
    scored = [
        (r.model, MEASURED_MRR[r.model])
        for r in RERANK_CHAIN
        if r.model in MEASURED_MRR and r.model not in ORDERED_ON_BREADTH_NOT_QUORA
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


def test_cohere_outranks_voyage_on_breadth_even_though_quora_disagrees():
    """The position ORDERED_ON_BREADTH_NOT_QUORA removes from the MRR check.

    Excluding it from one test must not leave it pinned by nothing - a
    decision defended only by a comment is a decision that quietly reverts.

    Slice 6 put Cohere BELOW rerank-3-lite on ONE corpus: 0.669 against 0.725
    on `quora`, 82 chunks and saturated. v2's G20 added three more corpora and
    that did not reproduce - Cohere gains +6.0q and is the only reranker
    measured that has NEVER hurt a corpus, while it rescues `gson`, the one
    corpus flash-lite decisively hurts, by 5.8 queries.

    `rerank-3` sitting above it has never been scored on any corpus at all.
    """
    order = [r.model for r in RERANK_CHAIN]

    assert order.index("rerank-v4.0-fast") < order.index("rerank-3-lite"), (
        "Cohere was demoted below Voyage again - that ordering comes from "
        "quora alone, and three more corpora did not reproduce it"
    )


def _env_names(tier) -> set[str]:
    """Every environment variable a shipped rerank tier reads at call time."""
    if isinstance(tier, LLMReranker):
        # Its key lives inside the `complete` callable, which cannot be read
        # back - so name the accounts the assembled chain is built from.
        return set(GOOGLE_KEYS)
    assert isinstance(tier, HTTPReranker), (
        f"{tier!r} is neither an LLMReranker nor an HTTPReranker, so this test "
        f"cannot tell which secrets it needs - teach _env_names about it"
    )
    return {
        name
        for name in (tier.api_key_env, tier.account_env, getattr(tier, "url_env", None))
        if name
    }


def test_every_env_var_the_shipped_rerank_chain_reads_is_mapped_in_the_smoke_workflow():
    """A GitHub secret is only STORED there. It reaches the test process only
    if smoke.yaml passes it in, and a missing line fails as "is not set" - the
    same message as a missing secret, so it reads like a dead provider.

    FOUND 2026-09-29: VOYAGE_API_KEY existed as a secret since 2026-08-11 and
    smoke.yaml never had a line for it, so both Voyage tiers failed four
    Mondays running. The two older mapping tests missed it because they walk
    the generator CHAIN and the embedder MIGRATION, and the rerankers are
    neither - Cohere only escaped because it is also an embedder.

    This walks the ASSEMBLED chain the ask path calls, not RERANK_CHAIN and
    LLM_RERANK_ORDER separately: two lists that are each complete can leave a
    hole between them, and Jev sat in exactly that hole until 2026-09-19.
    """
    assert SHIPPED_CHAIN, "the shipped chain is empty, so this test proves nothing"
    workflow = SMOKE_WORKFLOW.read_text(encoding="utf-8")

    required = set().union(*(_env_names(tier) for tier in SHIPPED_CHAIN))
    # Premises with a literal on one side, so an emptied set fails here rather
    # than passing vacuously.
    assert {"VOYAGE_API_KEY", "COHERE_API_KEY", "JEV_PROXY_URL"} <= required

    missing = sorted(
        name
        for name in required
        if f"{name}: ${{{{ secrets.{name} }}}}" not in workflow
    )

    assert not missing, missing


@CASES
@pytest.mark.parametrize("status", [429, 503])
@responses.activate
def test_every_reranker_reports_the_http_status_as_a_field(
    reranker, status, monkeypatch
):
    """The status has to be readable WITHOUT parsing the message.

    The weekly smoke run retries a 503 and treats a persistent 429 as a spent
    quota, and it can only do that if the error says which one it was.
    """
    monkeypatch.setenv(reranker.api_key_env, "test-key")
    if reranker.account_env:
        monkeypatch.setenv(reranker.account_env, "test-account")
    responses.add(responses.POST, reranker._endpoint(), json={"e": "x"}, status=status)

    with pytest.raises(RerankError) as raised:
        reranker.rank("why", ["a document"])

    assert raised.value.status == status
