from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from labpilot.sources import open_folder, open_git, open_zip, walk


@pytest.fixture
def openers(tmp_path, monkeypatch):
    folder = tmp_path / "folder-repo"
    folder.mkdir()
    (folder / "a.py").write_text("x = 1", encoding="utf-8")

    archive = tmp_path / "zip-repo.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a.py", "x = 1")

    def fake_run(command, **kwargs):
        clone = Path(command[-1])
        clone.mkdir(parents=True, exist_ok=True)
        (clone / "a.py").write_text("x = 1", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("labpilot.sources.git.subprocess.run", fake_run)

    return {
        "folder": lambda: open_folder(folder),
        "zip": lambda: open_zip(archive),
        "git": lambda: open_git("https://github.com/a1mohamad/git-repo"),
    }


@pytest.mark.parametrize("kind", ["folder", "zip", "git"])
def test_every_opener_yields_a_usable_source(kind, openers):
    with openers[kind]() as source:
        assert source.name
        assert source.root.is_absolute()
        assert source.root.is_dir()
        assert [found.relpath for found in walk(source)] == ["a.py"]


@pytest.mark.parametrize("kind", ["folder", "zip", "git"])
def test_every_opener_names_the_source_after_the_thing_it_opened(kind, openers):
    with openers[kind]() as source:
        assert source.name == f"{kind}-repo"


@pytest.mark.parametrize("kind", ["zip", "git"])
def test_a_temporary_source_is_deleted_afterwards(kind, openers):
    with openers[kind]() as source:
        root = source.root

    assert not root.exists()


def test_a_folder_source_is_never_deleted(openers):
    with openers["folder"]() as source:
        root = source.root

    assert root.is_dir()
    assert (root / "a.py").read_text(encoding="utf-8") == "x = 1"
