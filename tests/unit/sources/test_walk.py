from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from labpilot.sources import walk
from labpilot.sources.contracts import Source
from labpilot.sources.defaults import MAX_FILE_BYTES
from labpilot.sources.errors import SourceTooLarge


def build(root: Path, files: dict[str, str]) -> Source:
    for relpath, text in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Source(name=root.name, root=root)


def relpaths(source: Source) -> list[str]:
    return [found.relpath for found in walk(source)]


def test_a_skipped_directory_is_never_descended_into(tmp_path):
    source = build(
        tmp_path,
        {
            "train.py": "x = 1",
            "node_modules/left_pad/index.py": "x = 2",
            "src/.venv/lib.py": "x = 3",
            "src/model.py": "x = 4",
        },
    )

    assert relpaths(source) == ["train.py", "src/model.py"]


def test_directories_are_visited_in_sorted_order(tmp_path):
    source = build(
        tmp_path,
        {"zebra/a.py": "1", "alpha/a.py": "2", "middle/a.py": "3"},
    )

    assert relpaths(source) == ["alpha/a.py", "middle/a.py", "zebra/a.py"]


def test_subfolders_are_sorted_even_when_the_filesystem_is_not(tmp_path, monkeypatch):
    visited: list[str] = []

    def unsorted_walk(root, **kwargs):
        dirnames = ["zebra", "alpha", "middle"]
        yield str(tmp_path), dirnames, []
        for name in dirnames:
            visited.append(name)
            yield str(tmp_path / name), [], []

    monkeypatch.setattr("labpilot.sources._walk.os.walk", unsorted_walk)

    list(walk(Source(name="repo", root=tmp_path)))

    assert visited == ["alpha", "middle", "zebra"]


def test_an_unreadable_type_is_skipped_and_counted(tmp_path):
    source = build(
        tmp_path,
        {"a.py": "1", "logo.png": "not really a png", "data.bin": "x"},
    )

    assert relpaths(source) == ["a.py"]
    assert source.skipped == {"unreadable type": 2}


def test_walking_twice_does_not_double_count_skips(tmp_path):
    source = build(tmp_path, {"a.py": "1", "logo.png": "x"})

    list(walk(source))
    list(walk(source))

    assert source.skipped == {"unreadable type": 1}


@pytest.mark.skipif(
    sys.platform == "win32", reason="creating a symlink needs admin rights"
)
def test_a_symlinked_file_is_skipped(tmp_path):
    secret = tmp_path / "secret.py"
    secret.write_text("GOOGLE_API_KEY = 'real'", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "notes.py").write_text("x = 1", encoding="utf-8")
    os.symlink(secret, repo / "link.py")

    source = Source(name="repo", root=repo)

    assert relpaths(source) == ["notes.py"]
    assert source.skipped == {"symlink": 1}


def test_a_file_over_the_size_limit_is_skipped_and_counted(tmp_path):
    huge = "x" * 1_000_001
    assert len(huge.encode("utf-8")) > MAX_FILE_BYTES

    source = build(tmp_path, {"big.py": huge, "small.py": "x = 1"})

    assert relpaths(source) == ["small.py"]
    assert source.skipped == {"too big": 1}


def test_too_many_files_refuses_instead_of_truncating(tmp_path, monkeypatch):
    monkeypatch.setattr("labpilot.sources._walk.MAX_FILES", 2)
    source = build(tmp_path, {"a.py": "1", "b.py": "2", "c.py": "3"})

    with pytest.raises(SourceTooLarge, match="more than 2 readable files"):
        list(walk(source))


def test_too_much_text_refuses_instead_of_truncating(tmp_path, monkeypatch):
    monkeypatch.setattr("labpilot.sources._walk.MAX_TOTAL_BYTES", 10)
    source = build(tmp_path, {"a.py": "12345", "b.py": "12345", "c.py": "12345"})

    with pytest.raises(SourceTooLarge, match="bytes of readable text"):
        list(walk(source))


def test_an_unreadable_directory_is_counted_and_not_silently_dropped(
    tmp_path, monkeypatch
):
    def refusing_walk(root, **kwargs):
        kwargs["onerror"](PermissionError(13, "Permission denied", str(root)))
        yield str(tmp_path), [], ["a.py"]

    monkeypatch.setattr("labpilot.sources._walk.os.walk", refusing_walk)
    (tmp_path / "a.py").write_text("x = 1", encoding="utf-8")
    source = Source(name="repo", root=tmp_path)

    assert relpaths(source) == ["a.py"]
    assert source.skipped == {"unreadable directory": 1}


def test_a_file_that_cannot_be_inspected_is_counted_and_does_not_stop_the_walk(
    tmp_path, monkeypatch
):
    source = build(tmp_path, {"locked.py": "x = 1", "fine.py": "y = 2"})
    real_stat = Path.stat

    def refusing_stat(self, *args, **kwargs):
        if self.name == "locked.py":
            raise PermissionError(13, "Permission denied", str(self))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refusing_stat)

    assert relpaths(source) == ["fine.py"]
    assert source.skipped == {"unreadable file": 1}
