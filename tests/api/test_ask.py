"""The question embed: which model, which task, and how it fails.

No database and no network: these pin the pure decisions inside the search
path, which are the ones that fail SILENTLY rather than loudly. The rerank
cut and the two number spaces live in test_rank_pile.py.
"""

from __future__ import annotations

import pytest

from labpilot.api import searching
from labpilot.api.errors import EmbeddingUnavailable
from labpilot.embed import EmbeddingError
from labpilot.embed.contracts import EmbeddingBatch

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
    monkeypatch.setattr(searching, "MIGRATION", tuple(embedders))


def test_a_question_is_embedded_as_a_QUERY_and_never_as_a_document(monkeypatch):
    """A question is a REQUEST; a chunk is a STATEMENT.

    The providers that model that asymmetry rank measurably better for it, and
    getting it wrong costs NOTHING VISIBLE - the search still returns fifty
    rows, just worse ones. Nothing raises, so only a test can hold it.
    """
    embedder = FakeEmbedder("codestral-embed")
    only(monkeypatch, embedder)

    searching._embed_question("why do they diverge?", model="codestral-embed")

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

    vector = searching._embed_question("a question", model="mistral-embed")

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
        searching._embed_question("a question", model="retired-embed")


def test_an_embedder_that_fails_is_OUR_outage_not_the_users_mistake(monkeypatch):
    """EmbeddingError is not an ApiError, so unmapped it reaches the 500
    handler and reads as our bug. It IS our bug in a sense - the provider is
    down - but the caller needs a 503 that says so, not an opaque 500."""

    class Broken(FakeEmbedder):
        def embed(self, texts, *, task="document"):
            raise EmbeddingError("codestral is down")

    only(monkeypatch, Broken("codestral-embed"))

    with pytest.raises(EmbeddingUnavailable, match="codestral is down"):
        searching._embed_question("a question", model="codestral-embed")


class Busy(FakeEmbedder):
    def __init__(self, model, failures, status):
        super().__init__(model)
        self.failures = failures
        self.status = status
        self.tries = 0

    def embed(self, texts, *, task="document"):
        self.tries += 1
        if self.tries <= self.failures:
            raise EmbeddingError("busy", status=self.status)
        return super().embed(texts, task=task)


def test_a_busy_embedder_is_waited_for_and_asked_again(monkeypatch):
    # R10: a 429 on a query embed lost the whole answer on 2026-10-24.
    waits = []
    monkeypatch.setattr(searching.time, "sleep", waits.append)
    busy = Busy("codestral-embed", failures=2, status=429)
    only(monkeypatch, busy)

    searching._embed_question("a question", model="codestral-embed")

    assert busy.tries == 3
    assert waits == list(searching.EMBED_WAITS)


def test_an_embedder_still_busy_after_the_waits_is_an_outage(monkeypatch):
    monkeypatch.setattr(searching.time, "sleep", lambda s: None)
    busy = Busy("codestral-embed", failures=9, status=503)
    only(monkeypatch, busy)

    with pytest.raises(EmbeddingUnavailable):
        searching._embed_question("a question", model="codestral-embed")

    assert busy.tries == len(searching.EMBED_WAITS) + 1


def test_a_refusal_that_waiting_cannot_fix_is_not_waited_for(monkeypatch):
    monkeypatch.setattr(searching.time, "sleep", lambda s: pytest.fail("no wait"))
    busy = Busy("codestral-embed", failures=9, status=401)
    only(monkeypatch, busy)

    with pytest.raises(EmbeddingUnavailable):
        searching._embed_question("a question", model="codestral-embed")

    assert busy.tries == 1
