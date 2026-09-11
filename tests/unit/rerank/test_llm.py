from __future__ import annotations

import pytest

from labpilot.rerank import LLMReranker, RerankError

DOCS = ("alpha", "bravo", "charlie", "delta")


def build(reply: str = "2, 1, 3, 4", **kw) -> tuple[LLMReranker, list]:
    """The reranker AND the log of what it sent.

    Returned as a pair rather than attached to the object, because the
    dataclass is `slots=True` and has no __dict__ to hang a test field on.
    """
    sent: list[tuple[str, int]] = []

    def complete(prompt: str, budget: int) -> str:
        sent.append((prompt, budget))
        return reply

    rr = LLMReranker(complete=complete, name="Test LLM", model="test-model", **kw)
    return rr, sent


def reranker(reply: str = "2, 1, 3, 4", **kw) -> LLMReranker:
    return build(reply, **kw)[0]


def test_the_documents_are_labelled_from_one_not_zero():
    """Measured: with [0]..[3] a model answered "3, 1, 0, 4" - reading the
    labels as zero-based and one-based in the same reply."""
    rr, sent = build()
    rr.rank("why", DOCS)

    prompt = sent[0][0]
    assert "[1]\nalpha" in prompt
    assert "[4]\ndelta" in prompt
    assert "[0]" not in prompt


def test_a_one_based_reply_is_read_back_as_zero_based_positions():
    assert reranker("2, 1, 3, 4").rank("why", DOCS).order == (1, 0, 2, 3)


def test_the_answer_is_taken_from_the_END_of_a_reply_that_reasons_first():
    """The bug that made this project record a working model as unusable.

    A model that walks the chunks in order before answering writes "Chunk [1]
    ... Chunk [2] ..." first, so a left-to-right scan returns the identity
    order and the ranking is silently discarded.
    """
    reply = (
        "*   Chunk [1]: alpha (irrelevant).\n"
        "*   Chunk [2]: bravo (irrelevant).\n"
        "*   Chunk [3]: charlie (this one answers it).\n"
        "*   Chunk [4]: delta (irrelevant).\n"
        "\n*   Best: [3]\n*   3, 1, 2, 4"
    )

    assert reranker(reply).rank("why", DOCS).order == (2, 0, 1, 3)


def test_a_document_the_model_never_mentioned_keeps_its_retrieval_place():
    """The model expressed no opinion about it, so search's order stands."""
    assert reranker("3, 1").rank("why", DOCS).order == (2, 0, 1, 3)


def test_a_number_that_was_never_sent_is_ignored_rather_than_trusted():
    assert reranker("2, 99, 1, 3, 4").rank("why", DOCS).order == (1, 0, 2, 3)


def test_a_repeated_number_is_counted_once():
    """Ranking() would refuse a duplicate outright, so repairing it here is
    what keeps one sloppy reply from costing the whole ranking."""
    assert reranker("2, 2, 1, 3, 4").rank("why", DOCS).order == (1, 0, 2, 3)


def test_an_empty_ranking_is_a_DECLINE_and_keeps_the_retrieval_order():
    """gemma-4-26b-a4b returns a bare "[]" on about one query in 17.

    It is schema-valid and an opinion about nothing, so the honest reading is
    that retrieval's order stands - which is what skip() means. Raising would
    throw away every other answer in the run, and it did before this existed.
    """
    rr = reranker("[]")

    assert rr.rank("why", DOCS).order == (0, 1, 2, 3)
    assert rr.declined == 1


def test_declines_are_counted_because_MRR_cannot_see_them():
    """A decline scores exactly like not reranking, so a model that abstains
    looks average rather than broken. The rate is only visible if counted."""
    rr = reranker("[]")
    for _ in range(3):
        rr.rank("why", DOCS)

    assert rr.declined == 3


def test_top_n_cuts_the_order_after_it_is_built():
    assert reranker("4, 3, 2, 1").rank("why", DOCS, top_n=2).order == (3, 2)


def test_a_failure_from_the_callers_layer_becomes_our_error_type():
    """rerank/ cannot see LLMError - that is the layering rule working - so the
    wrap here is what lets the chain treat a dead LLM tier like any other."""

    def broken(prompt: str, budget: int) -> str:
        raise RuntimeError("the provider exploded")

    rr = LLMReranker(complete=broken, name="Test LLM", model="test-model")

    with pytest.raises(RerankError, match="the provider exploded"):
        rr.rank("why", DOCS)


def test_a_caller_bug_still_crashes_rather_than_degrading():
    rr, sent = build()

    with pytest.raises(ValueError, match="must not be blank"):
        rr.rank("   ", DOCS)
    with pytest.raises(ValueError, match="no documents to rank"):
        rr.rank("why", [])

    assert sent == []  # a caller's bug must cost no provider call
