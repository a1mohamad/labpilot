from __future__ import annotations

import pytest

from labpilot.api.services import ingest_artifact
from labpilot.embed.contracts import EmbeddingBatch
from labpilot.store import search

pytestmark = pytest.mark.database

CODE = b"CLIP_NORM = 1.5\n\n\ndef train():\n    return CLIP_NORM\n"


class FakeEmbedder:
    name, model, dim = "Fake", "fake-embed", 3

    def embed(self, texts, *, task="document"):
        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, float(i)) for i, _ in enumerate(texts)),
            model=self.model,
            dim=self.dim,
            prompt_tokens=0,
        )


@pytest.fixture
def only_fake(monkeypatch):
    """No provider is called. This test is about the WIRING, not the model."""
    fake = FakeEmbedder()
    monkeypatch.setattr(
        "labpilot.api.services._pick_embedder", lambda **kw: (fake, 0.1)
    )
    return fake


def test_a_file_becomes_rows_that_can_be_searched_back(db, only_fake):
    """The whole point of piece 2: store it, then FIND it.

    Chunk ids are what a citation resolves through, so this also proves the
    ingest path writes real chunk_index values rather than row positions.
    """
    result = ingest_artifact(db, CODE, name="train.py", side="B")

    assert result.chunks > 0
    assert result.artifact.embedding_model == "fake-embed"

    hits = search(db, result.artifact.id, (1.0, 0.0, 0.0), model="fake-embed")

    assert hits
    assert {h.chunk_index for h in hits} <= {c for c in range(result.chunks)}
    assert any("CLIP_NORM" in h.text for h in hits)


def test_ingesting_the_same_file_twice_leaves_one_corpus(db, only_fake):
    """The id is a content hash and write_artifact deletes first, so a repeat
    upload REPLACES. Without that, asking one question would search two copies
    of the same code."""
    first = ingest_artifact(db, CODE, name="train.py", side="B")
    second = ingest_artifact(db, CODE, name="train.py", side="B")

    assert first.artifact.id == second.artifact.id

    with db.cursor() as cur:
        cur.execute(
            "select count(*) from chunks where artifact_id = %s", (first.artifact.id,)
        )
        assert cur.fetchone()[0] == first.chunks
