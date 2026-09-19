"""The two number spaces, and the cut that depends on which path ran.

No database and no network: these pin the pure decisions inside the ask path,
which are the ones that fail SILENTLY rather than loudly.
"""

from __future__ import annotations

import pytest

from labpilot.api import services
from labpilot.api.errors import EmbeddingUnavailable
from labpilot.embed import EmbeddingError
from labpilot.embed.contracts import EmbeddingBatch
from labpilot.rerank import SKIP, Ranking
from labpilot.store import SearchHit

FIRST_ID = 100


def hit(index: int, score: float = 0.5) -> SearchHit:
    """Chunk ids start at 100, never at 0.

    Slice 5 learned this: a fixture numbered from zero cannot tell a chunk_index
    from a list position, because both are small integers. Offsetting makes the
    confusion provable instead of plausible.
    """
    return SearchHit(
        chunk_index=FIRST_ID + index,
        text=f"chunk {FIRST_ID + index}",
        header=f"[train.py - part {index}]",
        source="train.py",
        start_line=index * 10,
        end_line=index * 10 + 5,
        score=score,
    )


def test_a_reranked_position_is_read_as_a_position_and_never_as_an_id():
    """THE TRAP THIS WHOLE STEP IS BUILT AROUND.

        SearchHit.chunk_index   an ID in the corpus
        Ranking.order           POSITIONS into the list we just passed

    They are both small integers and they mean different things. `hits[p]` is
    right; treating `p` as an id cites the wrong file and line with complete
    confidence, and nothing raises.
    """
    hits = tuple(hit(i) for i in range(3))
    reversed_order = Ranking(order=(2, 1, 0), model="fake-rerank")

    best = services._best("q", hits, rank=lambda *_, **__: reversed_order)

    assert [h.chunk_index for h in best] == [102, 101, 100]


def test_a_skipped_rerank_keeps_the_VECTOR_number_not_the_reranked_one():
    """skip() truncates to whatever top_n it is handed, so we must not hand it one.

    If every tier fails, the chain returns the retrieval order unchanged - and
    cutting that to RERANK_TOP_N would apply a number calibrated for a path
    that did not run. Ranking carries model=SKIP, so the cut is made on the
    visible fact rather than on a guess.
    """
    hits = tuple(hit(i) for i in range(40))
    declined = Ranking(order=tuple(range(40)), model=SKIP)

    best = services._best("q", hits, rank=lambda *_, **__: declined)

    assert len(best) == services.VECTOR_TOP_N


def test_the_cut_is_never_handed_DOWN_to_the_rerank_chain():
    """The other half of the skip rule, and it was unguarded.

    Its neighbour above pins the CUT - VECTOR_TOP_N when the ranking is a
    skip. This pins the CALL: rank() must be asked for everything, because
    skip() truncates to whatever top_n it is given and would then apply the
    reranked number to a path that never reranked.

    The neighbour cannot catch it, because it injects a rank that returns a
    full ranking and so never observes the argument. Found by a mutation that
    handed top_n down and broke nothing at all.
    """
    hits = tuple(hit(index) for index in range(40))
    seen: dict[str, int | None] = {}

    def recording(question, documents, *, top_n):
        seen["top_n"] = top_n
        # what skip() really does with whatever it is handed
        order = tuple(range(len(documents)))[: top_n or len(documents)]
        return Ranking(order=order, model=SKIP)

    best = services._best("q", hits, rank=recording)

    assert seen["top_n"] is None, "asking for fewer would truncate the degraded path"
    assert len(best) == services.VECTOR_TOP_N


def test_a_real_reranker_cuts_to_the_reranked_number():
    """The other half: when a tier DID order them, the tighter cut is earned."""
    hits = tuple(hit(i) for i in range(40))
    ordered = Ranking(order=tuple(range(40)), model="rerank-3-lite")

    best = services._best("q", hits, rank=lambda *_, **__: ordered)

    assert len(best) < services.VECTOR_TOP_N


def test_the_reranker_reads_only_the_WINDOW_not_everything_search_returned():
    """RERANK_WINDOW is the measured cut, and it is invisible unless recorded.

    Search returns SEARCH_LIMIT per side; the reranker is handed the top
    RERANK_WINDOW of those. Measured 2026-09-18 on 5 Python corpora: the
    shipped w50 is nearly half as good as w20, and w10/w20/w30 are within
    0.17 queries of each other.

    Its neighbours cannot catch this. They inject a rank() that returns a full
    ranking and never look at the ARGUMENT, so handing the reranker all 40
    hits breaks none of them - proven by a mutation that deleted the cut and
    left 757 tests green.
    """
    hits = tuple(hit(index) for index in range(40))
    seen: dict[str, int] = {}

    def recording(question, documents, *, top_n):
        seen["documents"] = len(documents)
        return Ranking(order=tuple(range(len(documents))), model="rerank-3-lite")

    services._best("q", hits, rank=recording)

    assert seen["documents"] == services.RERANK_WINDOW


def test_nothing_found_is_not_an_error():
    """An empty result is an answer. Reranking nothing would be a ValueError."""
    assert services._best("q", ()) == []


# --- the query embed: which model, which task, and how it fails -------------


class FakeEmbedder:
    """Records what it was asked for. Nothing here reaches a provider."""

    def __init__(self, model: str, value: float = 1.0) -> None:
        self.model = model
        self.name = f"Fake {model}"
        self.value = value
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def embed(self, texts, *, task: str = "document"):
        self.calls.append((tuple(texts), task))
        return EmbeddingBatch(
            vectors=((self.value, 0.0, 0.0),),
            model=self.model,
            dim=3,
            prompt_tokens=0,
        )


def only(monkeypatch, *embedders: FakeEmbedder) -> None:
    monkeypatch.setattr(services, "MIGRATION", tuple(embedders))


def test_a_question_is_embedded_as_a_QUERY_and_never_as_a_document(monkeypatch):
    """A question is a REQUEST; a chunk is a STATEMENT.

    The providers that model that asymmetry rank measurably better for it, and
    getting it wrong costs NOTHING VISIBLE - the search still returns fifty
    rows, just worse ones. Nothing raises, so only a test can hold it.
    """
    embedder = FakeEmbedder("codestral-embed")
    only(monkeypatch, embedder)

    services._embed_question("why do they diverge?", model="codestral-embed")

    ((texts, task),) = embedder.calls
    assert task == "query"
    assert texts == ("why do they diverge?",)


def test_the_question_goes_to_the_embedder_THAT_MATCHES_the_stored_model(monkeypatch):
    """Two artifacts may hold two different embedders, and mixing is allowed.

    The lookup is by model NAME, not by position, so the corpus decides. Using
    the first embedder in MIGRATION instead would put the question in a
    different vector space from the rows it is compared against - and cosine
    similarity across two spaces is noise that still sorts and still returns
    a confident top fifty.
    """
    first = FakeEmbedder("codestral-embed", value=1.0)
    second = FakeEmbedder("mistral-embed", value=2.0)
    only(monkeypatch, first, second)

    vector = services._embed_question("a question", model="mistral-embed")

    assert vector == (2.0, 0.0, 0.0)
    assert first.calls == [], "the wrong space must not be asked"
    assert len(second.calls) == 1


def test_a_corpus_whose_embedder_is_gone_is_refused_and_not_searched_anyway(
    monkeypatch,
):
    """MIGRATION is a migration ORDER, and models leave it.

    A corpus stored with a model we no longer carry cannot be questioned at
    all - there is no way to put the question in its space. Falling back to
    any other embedder would search noise and answer confidently, so the only
    honest outcome is a refusal that names the model.
    """
    only(monkeypatch, FakeEmbedder("codestral-embed"))

    with pytest.raises(EmbeddingUnavailable, match="retired-embed"):
        services._embed_question("a question", model="retired-embed")


def test_an_embedder_that_fails_is_OUR_outage_not_the_users_mistake(monkeypatch):
    """EmbeddingError is not an ApiError, so unmapped it reaches the 500
    handler and reads as our bug. It IS our bug in a sense - the provider is
    down - but the caller needs a 503 that says so, not an opaque 500."""

    class Broken(FakeEmbedder):
        def embed(self, texts, *, task="document"):
            raise EmbeddingError("codestral is down")

    only(monkeypatch, Broken("codestral-embed"))

    with pytest.raises(EmbeddingUnavailable, match="codestral is down"):
        services._embed_question("a question", model="codestral-embed")
