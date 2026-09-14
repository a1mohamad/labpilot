from __future__ import annotations

import pytest

from labpilot.api.errors import EmbeddingUnavailable
from labpilot.api.services import (
    _artifact_id,
    _pick_embedder,
    _records,
    _source_id,
)
from labpilot.embed import MAX_BATCH_SIZE, MIGRATION
from labpilot.embed.contracts import EmbeddingBatch
from labpilot.ingest import Chunk, chunk_bytes

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


# --- _source_id: a whole repository, hashed from what was really READ --------


def repo_chunks(
    files: dict[str, str], *, artifact_id: str = "repo"
) -> tuple[Chunk, ...]:
    """Chunks as chunk_source would hand them over, from a {path: text} map.

    `artifact_id` is what the OPENER named the source - "my-repo.zip" for an
    archive, "my-repo" for a clone. _source_id must ignore it, which is the
    whole point of the tests below.
    """
    return tuple(
        Chunk(
            text=text,
            source=path,
            start_line=1,
            end_line=1 + text.count("\n"),
            side="B",
            artifact_id=artifact_id,
            chunk_index=index,
            header=f"[{path}]",
        )
        for index, (path, text) in enumerate(files.items())
    )


FILES = {"src/train.py": "lr = 3e-4\n", "README.md": "# Title\n"}


def test_the_same_repository_always_gets_the_same_id():
    assert _source_id(repo_chunks(FILES), "B") == _source_id(repo_chunks(FILES), "B")


def test_the_same_repository_as_a_zip_and_as_a_clone_is_ONE_artifact():
    """The id is hashed from the CONTENT, never from the archive's bytes.

    A zip and a git clone of the same commit give different container bytes
    and different source NAMES, so an id taken from either would store the
    same repository twice - and every later question would search one of the
    two copies with nothing reporting it.
    """
    as_zip = repo_chunks(FILES, artifact_id="my-repo.zip")
    as_clone = repo_chunks(FILES, artifact_id="my-repo")

    assert _source_id(as_zip, "B") == _source_id(as_clone, "B")


def test_moving_a_file_changes_the_id_even_when_the_text_does_not():
    """The PATH is hashed as well as the text.

    Two repositories can hold identical files in different places, and that
    is a different repository - `src/train.py` and `old/train.py` are not the
    same artifact, so a re-ingest must not silently replace one with the other.
    """
    moved = {"old/train.py": FILES["src/train.py"], "README.md": FILES["README.md"]}

    assert _source_id(repo_chunks(FILES), "B") != _source_id(repo_chunks(moved), "B")


def test_changing_one_line_changes_the_id():
    edited = {**FILES, "src/train.py": "lr = 1e-3\n"}

    assert _source_id(repo_chunks(FILES), "B") != _source_id(repo_chunks(edited), "B")


def test_the_same_repository_on_two_sides_gets_two_ids():
    """Comparing a repository against ITSELF is a legal request - an earlier
    commit as A, the working tree as B. One id would make the two sides the
    same row and the comparison would have nothing to compare."""
    chunks = repo_chunks(FILES)

    assert _source_id(chunks, "A") != _source_id(chunks, "B")
    assert _source_id(chunks, "A").startswith("A-")
    assert _source_id(chunks, "B").startswith("B-")


def test_the_id_never_leaks_the_repository_into_a_database_key():
    """An id reaches logs, URLs and error messages. A user's private source
    must not be readable from it, so it is a digest and not a path."""
    secret = repo_chunks({"deploy/keys.py": "TOKEN = 'hunter2'\n"})
    artifact_id = _source_id(secret, "B")

    assert "hunter2" not in artifact_id
    assert "deploy" not in artifact_id
    assert len(artifact_id) == len("B-") + 16
