from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from stat import S_ISREG

from labpilot.sources.contracts import Source, SourceFile
from labpilot.sources.defaults import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    READABLE_SUFFIXES,
    SKIP_DIRECTORIES,
)
from labpilot.sources.errors import SourceTooLarge


def walk(source: Source) -> Iterator[SourceFile]:
    source.skipped.clear()
    kept = 0
    total = 0

    def unreadable(_: OSError) -> None:
        source.skip("unreadable directory")

    for directory, dirnames, filenames in os.walk(source.root, onerror=unreadable):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRECTORIES)

        for name in sorted(filenames):
            path = Path(directory) / name

            try:
                reason, size = _inspect(path)
            except OSError:
                source.skip("unreadable file")
                continue

            if reason:
                source.skip(reason)
                continue

            kept += 1
            total += size
            _check_budget(source, kept=kept, total=total)

            yield SourceFile(
                path=path,
                relpath=path.relative_to(source.root).as_posix(),
                size=size,
            )


def _inspect(path: Path) -> tuple[str | None, int]:
    if path.is_symlink():
        return "symlink", 0
    if path.suffix.lower() not in READABLE_SUFFIXES:
        return "unreadable type", 0

    described = path.stat()
    if not S_ISREG(described.st_mode):
        return "not a file", 0
    if described.st_size > MAX_FILE_BYTES:
        return "too big", 0

    return None, described.st_size


def _check_budget(source: Source, *, kept: int, total: int) -> None:
    if kept > MAX_FILES:
        raise SourceTooLarge(
            f"{source.name} holds more than {MAX_FILES} readable files"
        )
    if total > MAX_TOTAL_BYTES:
        raise SourceTooLarge(
            f"{source.name} holds more than {MAX_TOTAL_BYTES} bytes of readable text"
        )
