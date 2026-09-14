"""A whole repository, stored as ONE artifact, against a real database.

The single-file door is covered by test_ingest_artifact.py. What is different
here is that many files become one corpus, so the pair that the chunks table
uses as its PRIMARY KEY - (artifact_id, chunk_index) - has to stay unique
across file boundaries. That is a claim only a real database can settle:
tests/integration/test_a_repository_becomes_chunks.py proves the counter
produces unique indexes, and this proves Postgres accepts what it produces.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.api.errors import EmptyArtifact
from labpilot.api.services import ingest_source
from labpilot.embed.contracts import EmbeddingBatch
from labpilot.sources import open_folder
from labpilot.store import search

pytestmark = pytest.mark.database


class FakeEmbedder:
    """No provider is called. These tests are about the WIRING, not the model."""

    name, model, dim = "Fake", "fake-embed", 3

    def embed(self, texts, *, task="document"):
        return EmbeddingBatch(
            vectors=tuple((1.0, 0.0, float(index)) for index, _ in enumerate(texts)),
            model=self.model,
            dim=self.dim,
            prompt_tokens=0,
        )


@pytest.fixture
def only_fake(monkeypatch):
    monkeypatch.setattr(
        "labpilot.api.services._pick_embedder", lambda **kw: (FakeEmbedder(), 0.1)
    )


def build(root: Path, files: dict[str, str]) -> Path:
    for relpath, text in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def a_file_of(functions: int, marker: str) -> str:
    """Source long enough to become SEVERAL chunks, so the primary key is
    really exercised. One chunk per file would never cross a boundary."""
    body = "\n".join(f"    step_{n} = compute({n}) * 31 + offset" for n in range(40))
    return "\n\n".join(
        f"def {marker}_{index}(offset):\n{body}\n    return step_0\n"
        for index in range(functions)
    )


REPO = {
    "src/train.py": a_file_of(3, "train"),
    "src/model.py": a_file_of(3, "model"),
    "docs/README.md": "# Title\n\nCLIP_NORM is 1.5 in this project.\n",
}


def test_a_repository_becomes_rows_that_can_be_searched_back(db, only_fake, tmp_path):
    """Store many files as one corpus, then FIND them.

    If chunk_index restarted per file, write_artifact would fail here on a
    duplicate primary key - so this is the database half of the counter that
    the repository door added.
    """
    build(tmp_path / "repo", REPO)

    with open_folder(tmp_path / "repo") as source:
        result = ingest_source(db, source, side="B")

    assert result.chunks > 3, "the fixture must span several chunks per file"
    assert result.artifact.id.startswith("B-")
    assert result.artifact.name == "repo"

    hits = search(db, result.artifact.id, (1.0, 0.0, 0.0), model="fake-embed")

    assert hits
    assert {hit.source for hit in hits} <= set(REPO)
    assert len({hit.chunk_index for hit in hits}) == len(hits)


def test_every_file_of_the_repository_is_stored_not_only_the_first(
    db, only_fake, tmp_path
):
    """A generator that stops early loses every file after it, silently.

    The walk has been broken this way twice - an unreadable file and a broken
    notebook each aborted the whole ingest - so the corpus is checked here for
    the files it should CONTAIN, not merely for a row count.
    """
    build(tmp_path / "repo", REPO)

    with open_folder(tmp_path / "repo") as source:
        result = ingest_source(db, source, side="B")

    with db.cursor() as cur:
        cur.execute(
            "select distinct source from chunks where artifact_id = %s",
            (result.artifact.id,),
        )
        stored = {row[0] for row in cur.fetchall()}

    assert stored == set(REPO)


def test_re_ingesting_the_same_repository_leaves_one_corpus(db, only_fake, tmp_path):
    """The id is a content hash and write_artifact deletes first, so a repeat
    REPLACES. Without that, one question would search two copies of the same
    repository and every finding would arrive twice."""
    build(tmp_path / "repo", REPO)

    with open_folder(tmp_path / "repo") as source:
        first = ingest_source(db, source, side="B")
    with open_folder(tmp_path / "repo") as source:
        second = ingest_source(db, source, side="B")

    assert first.artifact.id == second.artifact.id

    with db.cursor() as cur:
        cur.execute(
            "select count(*) from chunks where artifact_id = %s", (first.artifact.id,)
        )
        assert cur.fetchone()[0] == first.chunks


def test_editing_one_file_stores_a_second_corpus_rather_than_overwriting(
    db, only_fake, tmp_path
):
    """A changed repository is a DIFFERENT artifact, because the id is hashed
    from the content. Comparing yesterday's clone against today's is the whole
    product, so the two must be able to sit in the table at once."""
    build(tmp_path / "before", REPO)
    build(tmp_path / "after", {**REPO, "src/train.py": a_file_of(3, "renamed")})

    with open_folder(tmp_path / "before") as source:
        before = ingest_source(db, source, side="B")
    with open_folder(tmp_path / "after") as source:
        after = ingest_source(db, source, side="B")

    assert before.artifact.id != after.artifact.id

    with db.cursor() as cur:
        cur.execute("select count(*) from artifacts")
        assert cur.fetchone()[0] == 2


def test_a_repository_with_nothing_readable_is_refused_not_stored_empty(
    db, only_fake, tmp_path
):
    """An empty corpus answers every question with "not found", confidently
    and forever. Refusing is the honest outcome, and it must happen BEFORE a
    row is written - a stored artifact holding no chunks is unsearchable and
    indistinguishable from a real one."""
    build(tmp_path / "repo", {"data.json": '{"rows": []}', "secrets.env": "KEY=x"})

    with open_folder(tmp_path / "repo") as source:
        with pytest.raises(EmptyArtifact, match="repo"):
            ingest_source(db, source, side="B")

    with db.cursor() as cur:
        cur.execute("select count(*) from artifacts")
        assert cur.fetchone()[0] == 0
