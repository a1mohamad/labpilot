from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest

from labpilot.api.config import ApiConfig
from labpilot.sources.defaults import (
    MAX_ARCHIVE_BYTES,
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


@pytest.mark.xfail(
    strict=True,
    reason="MAX_ARCHIVE_BYTES is 50MB while the API body limit is about 2MB, so "
    "an archive that size can never arrive. Harmless today because the endpoint "
    "accepts no archive; slice 7 must settle which number moves.",
)
def test_an_archive_we_accept_must_be_able_to_reach_us():
    assert MAX_ARCHIVE_BYTES <= ApiConfig.MAX_REQUEST_BODY_BYTES


def test_a_file_that_could_hold_secrets_or_data_is_never_readable():
    """.env holds API keys and must never be read, chunked, embedded, or sent
    to a provider. .json is usually a dataset, and a pretty-printed one has
    short lines, so the generated-file guard would not catch it either."""
    for suffix in (".env", ".json", ".csv", ".xml", ".lock"):
        assert suffix not in READABLE_SUFFIXES


def test_the_popular_languages_are_all_readable():
    for suffix in (
        ".js",
        ".ts",
        ".java",
        ".go",
        ".rs",
        ".cpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".r",
        ".jl",
        ".sql",
        ".sh",
        ".yaml",
    ):
        assert suffix in READABLE_SUFFIXES
