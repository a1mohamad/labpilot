from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from labpilot.api.services import chunk_source
from labpilot.prompts._ids import assign_ids
from labpilot.sources import open_folder


def build(root: Path, files: dict[str, str]) -> Path:
    for relpath, text in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_two_files_with_the_same_name_get_different_sources(tmp_path):
    build(
        tmp_path / "repo",
        {
            "src/utils.py": "def clean(text):\n    return text.strip()\n",
            "tests/utils.py": "def fixture():\n    return 1\n",
        },
    )

    with open_folder(tmp_path / "repo") as source:
        chunks = list(chunk_source(source, side="B"))

    assert {chunk.source for chunk in chunks} == {"src/utils.py", "tests/utils.py"}


def test_every_chunk_carries_the_repository_as_its_artifact_id(tmp_path):
    build(tmp_path / "my-repo", {"a.py": "x = 1", "deep/b.py": "y = 2"})

    with open_folder(tmp_path / "my-repo") as source:
        chunks = list(chunk_source(source, side="B"))

    assert {chunk.artifact_id for chunk in chunks} == {"my-repo"}
    assert {chunk.side for chunk in chunks} == {"B"}


def test_a_file_that_is_not_utf8_is_counted_and_does_not_stop_the_walk(tmp_path):
    repo = build(tmp_path / "repo", {"good.py": "x = 1", "later.py": "z = 3"})
    (repo / "broken.py").write_bytes(b"# caf\xe9 in latin-1\nx = 2\n")

    with open_folder(repo) as source:
        chunks = list(chunk_source(source, side="B"))
        skipped = dict(source.skipped)

    assert {chunk.source for chunk in chunks} == {"good.py", "later.py"}
    assert skipped == {"not utf-8": 1}


def test_chunks_are_streamed_and_never_built_as_one_list(tmp_path):
    build(tmp_path / "repo", {f"f{index}.py": f"x = {index}" for index in range(5)})

    with open_folder(tmp_path / "repo") as source:
        produced = chunk_source(source, side="B")

        assert isinstance(produced, Iterator)
        assert not isinstance(produced, list | tuple)
        assert next(produced).source == "f0.py"


def test_ids_across_a_repository_do_not_collide(tmp_path):
    build(
        tmp_path / "repo",
        {"src/utils.py": "x = 1", "tests/utils.py": "y = 2", "main.py": "z = 3"},
    )

    with open_folder(tmp_path / "repo") as source:
        chunks = tuple(chunk_source(source, side="B"))

    assigned = assign_ids(chunks)

    assert len(assigned) == len(chunks)
    assert sorted(assigned) == sorted(f"B-{index}" for index in range(len(chunks)))


def test_a_file_we_cannot_read_is_counted_and_does_not_stop_the_ingest(
    tmp_path, monkeypatch
):
    build(tmp_path / "repo", {"a.py": "x = 1", "locked.py": "y = 2", "z.py": "z = 3"})
    real_read_bytes = Path.read_bytes

    def refusing_read(self, *args, **kwargs):
        if self.name == "locked.py":
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", refusing_read)

    with open_folder(tmp_path / "repo") as source:
        chunks = list(chunk_source(source, side="B"))
        skipped = dict(source.skipped)

    assert {chunk.source for chunk in chunks} == {"a.py", "z.py"}
    assert skipped == {"unreadable file": 1}


def test_one_broken_notebook_does_not_abort_the_whole_ingest(tmp_path):
    # The slice 2 audit fixed this for unreadable FILES. A document whose
    # loader refuses is the same failure through a newer door: without the
    # LoaderError guard, one bad .ipynb in a repository loses every file
    # after it, silently, because chunk_source is a generator.
    build(
        tmp_path / "repo",
        {
            "a_first.py": "def first():\n    return 1\n",
            "b_broken.ipynb": "{ this is not json",
            "c_last.py": "def last():\n    return 2\n",
        },
    )

    with open_folder(tmp_path / "repo") as source:
        chunks = list(chunk_source(source, side="B"))

    sources = {chunk.source for chunk in chunks}
    assert sources == {"a_first.py", "c_last.py"}
    assert source.skipped["unreadable document"] == 1


def test_a_notebook_in_a_repository_becomes_real_cells(tmp_path):
    import json

    notebook = json.dumps(
        {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["## Training\n", "We train for ten epochs.\n"],
                },
                {
                    "cell_type": "code",
                    "source": ["train(epochs=10)\n"],
                    "outputs": [
                        {
                            "output_type": "stream",
                            "name": "stdout",
                            "text": ["final f1 0.8226\n"],
                        }
                    ],
                    "execution_count": 4,
                },
            ],
            "nbformat": 4,
        }
    )
    build(tmp_path / "repo", {"research/train.ipynb": notebook})

    with open_folder(tmp_path / "repo") as source:
        chunks = list(chunk_source(source, side="B"))

    joined = "\n".join(chunk.text for chunk in chunks)
    assert "We train for ten epochs." in joined
    assert "train(epochs=10)" in joined
    assert "final f1 0.8226" in joined
    assert '\n",' not in joined
    assert all(chunk.source == "research/train.ipynb" for chunk in chunks)


def test_a_real_paper_in_a_repository_is_ingested_not_skipped_as_too_big(tmp_path):
    """Real papers are 0.8-2.2MB. If MAX_FILE_BYTES ever falls back to 1MB the
    walk drops them as 'too big' -- and a skip raises nothing, so the corpus
    would quietly lose every paper it was given."""
    repo = build(tmp_path / "repo", {"train.py": "def train():\n    return 1\n"})
    paper = Path("data/samples/pdf/one_column.pdf")
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "paper.pdf").write_bytes(paper.read_bytes())

    with open_folder(repo) as source:
        chunks = list(chunk_source(source, side="A"))
        skipped = dict(source.skipped)

    assert skipped == {}
    assert {chunk.source for chunk in chunks} == {"docs/paper.pdf", "train.py"}
    assert any("page 1" in chunk.header for chunk in chunks)


def test_a_minified_file_is_skipped_and_counted_while_the_rest_is_ingested(tmp_path):
    """The one that matters: a repo full of good code plus one bundle must
    lose the bundle and keep everything else, with the skip counted."""
    repo = build(
        tmp_path / "repo",
        {
            "app.js": "function add(a, b) {\n  return a + b\n}\n",
            "main.go": "package main\n\nfunc main() {\n\tprintln(1)\n}\n",
            "bundle.min.js": "function a(b,c){return b+c};" * 3000,
        },
    )

    with open_folder(repo) as source:
        chunks = list(chunk_source(source, side="B"))
        skipped = dict(source.skipped)

    assert {chunk.source for chunk in chunks} == {"app.js", "main.go"}
    assert skipped == {"generated or minified": 1}
