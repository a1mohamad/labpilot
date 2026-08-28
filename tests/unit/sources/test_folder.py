from __future__ import annotations

import pytest

from labpilot.sources import walk
from labpilot.sources.errors import SourceNotFound
from labpilot.sources.folder import open_folder


def test_the_folder_name_becomes_the_artifact_name(tmp_path):
    repo = tmp_path / "my-repo"
    repo.mkdir()

    with open_folder(repo) as source:
        assert source.name == "my-repo"


def test_the_name_can_be_overridden(tmp_path):
    with open_folder(tmp_path, name="chosen") as source:
        assert source.name == "chosen"


def test_the_root_is_absolute_so_relative_paths_survive_a_chdir(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "train.py").write_text("x = 1", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    with open_folder(".") as source:
        assert source.root.is_absolute()
        monkeypatch.chdir(tmp_path.parent)
        assert [f.relpath for f in walk(source)] == ["src/train.py"]


def test_a_file_is_not_a_folder(tmp_path):
    single = tmp_path / "train.py"
    single.write_text("x = 1", encoding="utf-8")

    with pytest.raises(SourceNotFound, match="is not a folder"):
        with open_folder(single):
            pass


def test_a_missing_path_is_refused(tmp_path):
    with pytest.raises(SourceNotFound, match="is not a folder"):
        with open_folder(tmp_path / "nope"):
            pass
