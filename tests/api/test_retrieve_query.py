from types import SimpleNamespace

import pytest

from labpilot.api import searching
from labpilot.api.errors import ArtifactChanged
from labpilot.store import ModelMismatch, SearchHit


def hit(index):
    return SearchHit(
        chunk_index=index,
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index + 1,
        score=0.5,
    )


def sides():
    def stored(side):
        artifact = SimpleNamespace(id=f"{side}-9", embedding_model=f"model-{side}")
        return SimpleNamespace(artifact=artifact)

    return {"A": stored("A"), "B": stored("B")}


@pytest.fixture
def seen(monkeypatch):
    seen = {"embed": [], "search": [], "fuse": [], "rerank": []}

    def embed(text, *, model):
        seen["embed"].append((text, model))
        return (0.1, 0.2)

    def search(conn, artifact_id, vector, *, model, limit):
        seen["search"].append((artifact_id, model))
        return (hit(7), hit(8))

    def fuse(conn, artifact_id, text, dense):
        seen["fuse"].append((artifact_id, text))
        return dense

    def rerank(text, hits):
        seen["rerank"].append(text)
        return list(hits)

    monkeypatch.setattr(searching, "_embed_question", embed)
    monkeypatch.setattr(searching, "search", search)
    monkeypatch.setattr(searching, "_fused", fuse)
    monkeypatch.setattr(searching, "rank_pile", rerank)
    return seen


def test_the_search_text_is_embedded_and_fused_with_the_artifacts_own_model(seen):
    searching.retrieve_query(None, sides(), side="B", text="gradient clipping")

    assert seen["embed"] == [("gradient clipping", "model-B")]
    assert seen["fuse"] == [("B-9", "gradient clipping")]


def test_a_query_is_not_reranked_that_happens_once_per_side_after_the_merge(seen):
    searching.retrieve_query(None, sides(), side="B", text="gradient clipping")

    assert seen["rerank"] == []


def test_only_the_artifact_of_the_asked_side_is_searched(seen):
    searching.retrieve_query(None, sides(), side="A", text="learning rate")

    assert seen["search"] == [("A-9", "model-A")]


def test_every_chunk_comes_back_tagged_with_its_side_and_artifact(seen):
    chunks = searching.retrieve_query(None, sides(), side="B", text="seed")

    assert [(c.side, c.artifact_id, c.chunk_index) for c in chunks] == [
        ("B", "B-9", 7),
        ("B", "B-9", 8),
    ]


def test_a_reingest_with_another_embedder_is_our_409_and_not_a_crash(seen, monkeypatch):
    def mismatch(*args, **kwargs):
        raise ModelMismatch("changed")

    monkeypatch.setattr(searching, "search", mismatch)

    with pytest.raises(ArtifactChanged):
        searching.retrieve_query(None, sides(), side="B", text="seed")
