from __future__ import annotations

from pathlib import Path, PurePosixPath

from labpilot.api.config import ApiConfig
from labpilot.sources.defaults import (
    MAX_FILE_BYTES,
    READABLE_SUFFIXES,
    SKIP_DIRECTORIES,
)


def test_a_relative_path_uses_forward_slashes_on_every_platform():
    root = Path("repo")
    relpath = (root / "src" / "train.py").relative_to(root).as_posix()

    assert relpath == "src/train.py"
    assert "\\" not in relpath
    assert PurePosixPath(relpath).parts == ("src", "train.py")


def test_the_per_file_limit_is_not_larger_than_the_upload_limit():
    assert MAX_FILE_BYTES <= ApiConfig.MAX_UPLOAD_BYTES


def test_no_readable_suffix_is_also_a_skipped_directory():
    assert not {suffix.lstrip(".") for suffix in READABLE_SUFFIXES} & SKIP_DIRECTORIES
