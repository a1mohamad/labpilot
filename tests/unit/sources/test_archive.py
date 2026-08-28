from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from labpilot.sources import walk
from labpilot.sources.archive import _extract, open_zip
from labpilot.sources.errors import SourceNotFound, SourceTooLarge, UnsafeArchive


def make_zip(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, text in entries.items():
            bundle.writestr(name, text)
    return path


def test_a_zip_becomes_a_walkable_source(tmp_path):
    archive = make_zip(
        tmp_path / "my-repo.zip",
        {"src/train.py": "x = 1", "README.md": "# hi", "logo.png": "binary"},
    )

    with open_zip(archive) as source:
        assert source.name == "my-repo"
        assert [f.relpath for f in walk(source)] == ["README.md", "src/train.py"]
        assert source.skipped == {"unreadable type": 1}


def test_the_temporary_folder_is_deleted_afterwards(tmp_path):
    archive = make_zip(tmp_path / "r.zip", {"a.py": "x = 1"})

    with open_zip(archive) as source:
        root = source.root
        assert root.exists()

    assert not root.exists()


def test_the_temporary_folder_is_deleted_even_when_the_body_raises(tmp_path):
    archive = make_zip(tmp_path / "r.zip", {"a.py": "x = 1"})
    root = None

    with pytest.raises(RuntimeError):
        with open_zip(archive) as source:
            root = source.root
            raise RuntimeError("the caller exploded")

    assert root is not None
    assert not root.exists()


@pytest.mark.parametrize(
    "name",
    ["../escaped.py", "a/../../escaped.py", "/etc/passwd", "C:/Windows/x.py"],
)
def test_an_entry_that_leaves_the_folder_is_refused(tmp_path, name):
    archive = make_zip(tmp_path / "r.zip", {name: "x = 1", "ok.py": "x = 2"})

    with pytest.raises(UnsafeArchive, match="unsafe paths"):
        with open_zip(archive):
            pass


def test_a_declared_size_over_the_limit_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("labpilot.sources.archive.MAX_UNCOMPRESSED_BYTES", 100)
    archive = make_zip(tmp_path / "r.zip", {"a.py": "x" * 500})

    with pytest.raises(SourceTooLarge, match="declares"):
        with open_zip(archive):
            pass


def test_unpacking_stops_when_the_real_size_passes_the_limit(tmp_path, monkeypatch):
    # _extract is called directly on purpose: it is the only way to reach the
    # second guard, because a zip written by zipfile always declares the truth
    # and the first guard would refuse it before unpacking begins.
    monkeypatch.setattr("labpilot.sources.archive.MAX_UNCOMPRESSED_BYTES", 100)
    archive = make_zip(tmp_path / "r.zip", {"a.py": "x" * 500})
    root = tmp_path / "out"
    root.mkdir()

    with zipfile.ZipFile(archive) as bundle:
        with pytest.raises(SourceTooLarge, match="unpacked past"):
            _extract(bundle, root)


def test_an_archive_over_the_compressed_limit_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("labpilot.sources.archive.MAX_ARCHIVE_BYTES", 100)
    archive = make_zip(tmp_path / "r.zip", {"a.py": "x = 1"})
    assert archive.stat().st_size > 100

    with pytest.raises(SourceTooLarge, match="over the 100 limit"):
        with open_zip(archive):
            pass


def test_too_many_entries_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("labpilot.sources.archive.MAX_FILES", 2)
    archive = make_zip(tmp_path / "r.zip", {"a.py": "1", "b.py": "2", "c.py": "3"})

    with pytest.raises(SourceTooLarge, match="more than 2 entries"):
        with open_zip(archive):
            pass


def test_a_file_that_is_not_a_zip_is_refused(tmp_path):
    broken = tmp_path / "r.zip"
    broken.write_bytes(b"this is not a zip at all")

    with pytest.raises(UnsafeArchive, match="not a readable zip"):
        with open_zip(broken):
            pass


def test_a_missing_archive_is_refused(tmp_path):
    with pytest.raises(SourceNotFound, match="is not a file"):
        with open_zip(tmp_path / "nope.zip"):
            pass
