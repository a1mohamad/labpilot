from __future__ import annotations

import pytest

from labpilot.api.errors import EmbeddingUnavailable
from labpilot.api.services import _artifact_id, _pick_embedder, _records
from labpilot.embed import MAX_BATCH_SIZE, MIGRATION
from labpilot.embed.contracts import EmbeddingBatch
from labpilot.ingest import chunk_bytes

PAPER = b"# Title\n\nsome words about a method.\n"


class FakeEmbedder:
    """Returns a vector that IDENTIFIES the text it came from.

    Pairing chunks with vectors is the one thing _records can get silently
    wrong, so the fake makes a mismatch visible: vector[0] is the length of
    the text that produced it.
    """

    name = "Fake"
    model = "fake"
    dim = 2

    def __init__(self):
        self.batch_sizes: list[int] = []

    def embed(self, texts, *, task="document"):
        self.batch_sizes.append(len(texts))
        return EmbeddingBatch(
            vectors=tuple((float(len(t)), 1.0) for t in texts),
            model=self.model,
            dim=self.dim,
            prompt_tokens=0,
        )


def chunks(n: int):
    """EXACTLY n chunks - each paragraph is sized to become one on its own.

    The first version joined SHORT lines and let the chunker pack them, so a
    request for 60 produced 13 - and the one test that needs more than one
    BATCH was silently exercising a single batch.
    """
    body = "\n\n".join("word " * 250 for _ in range(n))
    return chunk_bytes(body.encode(), source="a.txt", side="B", artifact_id="id")


# ---------------------------------------------------------------- the id


def test_the_same_file_always_gets_the_same_id():
    """Ingest must be idempotent: write_artifact DELETES by id before it
    inserts, so a stable id turns a second upload into a replace rather than
    a duplicate corpus."""
    assert _artifact_id(PAPER, "A") == _artifact_id(PAPER, "A")


def test_the_same_file_on_two_sides_gets_two_ids():
    """One file can legitimately be BOTH the reference and the subject, and
    they must not overwrite each other."""
    assert _artifact_id(PAPER, "A") != _artifact_id(PAPER, "B")


def test_a_different_file_gets_a_different_id():
    assert _artifact_id(PAPER, "A") != _artifact_id(PAPER + b"!", "A")


def test_the_id_never_leaks_the_file_into_a_database_key():
    """It is a hash, not the name or the text - so an id is safe to log."""
    assert PAPER.decode().strip() not in _artifact_id(PAPER, "A")


# ------------------------------------------------------------ the pairing


def test_every_chunk_is_paired_with_its_own_vector():
    """THE invariant of _records, and the one that fails silently.

    The index must keep counting ACROSS batch boundaries: batch 2 starts at
    chunk 96, not back at chunk 0. Get it wrong and chunk 96 is stored with
    chunk 0's vector - nothing raises, and every later search is quietly
    wrong about which code it found.
    """
    embedder = FakeEmbedder()
    parts = chunks(120)
    assert len(parts) > MAX_BATCH_SIZE, f"premise: need >1 batch, got {len(parts)}"

    records = list(_records(embedder, parts))

    assert len(records) == len(parts)
    for chunk, record in zip(parts, records, strict=True):
        assert record.vector[0] == float(len(chunk.embed_text))
        assert record.chunk_index == chunk.chunk_index


def test_the_texts_are_sent_in_batches_not_all_at_once():
    """2,000 vectors held at once is ~73MB on a 512MB box."""
    embedder = FakeEmbedder()

    list(_records(embedder, chunks(120)))

    assert max(embedder.batch_sizes) <= MAX_BATCH_SIZE


# ------------------------------------------------------------ the choice


def test_a_model_that_cannot_finish_today_is_skipped():
    """BGE's daily neuron budget reports inf, and inf must not be chosen."""
    bge = next(e for e in MIGRATION if e.model == "@cf/baai/bge-base-en-v1.5")
    codestral = next(e for e in MIGRATION if e.model == "codestral-embed")

    picked, _ = _pick_embedder(
        tokens=5_000_000, chunks=15_000, candidates=(bge, codestral)
    )

    assert picked is codestral


def test_no_usable_model_is_a_failure_not_a_silent_pick():
    """Returning an inf model would start an ingest that cannot finish."""
    bge = next(e for e in MIGRATION if e.model == "@cf/baai/bge-base-en-v1.5")

    with pytest.raises(EmbeddingUnavailable, match="no embedder"):
        _pick_embedder(tokens=5_000_000, chunks=15_000, candidates=(bge,))


def test_a_small_corpus_keeps_the_strength_order():
    """Below the budget, quality decides - MIGRATION[0] is the best model."""
    picked, _ = _pick_embedder(tokens=20_000, chunks=60)

    assert picked is MIGRATION[0]
