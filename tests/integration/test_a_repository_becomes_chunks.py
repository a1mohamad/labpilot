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
