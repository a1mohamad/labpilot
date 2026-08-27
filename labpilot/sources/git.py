from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from labpilot.sources.contracts import Source
from labpilot.sources.defaults import CLONE_TIMEOUT_SECONDS
from labpilot.sources.errors import CloneFailed, UnsupportedURL


@contextmanager
def open_git(url: str, *, name: str | None = None) -> Generator[Source]:
    address = _validated(url)

    with tempfile.TemporaryDirectory(
        prefix="labpilot-", ignore_cleanup_errors=True
    ) as temporary:
        root = Path(temporary)
        _clone(address, root)

        yield Source(name=name or _repository_name(address), root=root)


def _validated(url: str) -> str:
    parsed = urlparse(url.strip())

    if parsed.scheme != "https":
        raise UnsupportedURL(
            f"only https:// addresses are accepted, got {parsed.scheme or 'none'!r}"
        )

    if not parsed.hostname:
        raise UnsupportedURL(f"{url!r} names no host")

    if parsed.username or parsed.password:
        raise UnsupportedURL("an address must not carry credentials")

    return parsed.geturl()


def _repository_name(url: str) -> str:
    tail = PurePosixPath(urlparse(url).path).name
    return tail.removesuffix(".git") or "repository"


def _clone(url: str, root: Path) -> None:
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--no-tags",
        "--quiet",
        "--",
        url,
        str(root),
    ]

    try:
        finished = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=False,
        )
    except FileNotFoundError as exc:
        raise CloneFailed("git is not installed on this machine") from exc
    except subprocess.TimeoutExpired as exc:
        raise CloneFailed(
            f"cloning {url} took longer than {CLONE_TIMEOUT_SECONDS} seconds"
        ) from exc

    if finished.returncode != 0:
        raise CloneFailed(f"could not clone {url}: {finished.stderr.strip()}")
