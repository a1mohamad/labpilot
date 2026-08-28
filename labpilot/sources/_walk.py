from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

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

    for directory, dirnames, filenames in os.walk(source.root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRECTORIES)

        for name in sorted(filenames):
            path = Path(directory) / name
            reason = _reason_to_skip(path)
            if reason:
                source.skipped[reason] = source.skipped.get(reason, 0) + 1
                continue

            size = path.stat().st_size
            kept += 1
            total += size
            _check_budget(source, kept=kept, total=total)

            yield SourceFile(
                path=path,
                relpath=path.relative_to(source.root).as_posix(),
                size=size,
            )


def _reason_to_skip(path: Path) -> str | None:
    if path.is_symlink():
        return "symlink"
    if path.suffix.lower() not in READABLE_SUFFIXES:
        return "unreadable type"
    if not path.is_file():
        return "not a file"
    if path.stat().st_size > MAX_FILE_BYTES:
        return "too big"
    return None


def _check_budget(source: Source, *, kept: int, total: int) -> None:
    if kept > MAX_FILES:
        raise SourceTooLarge(
            f"{source.name} holds more than {MAX_FILES} readable files"
        )
    if total > MAX_TOTAL_BYTES:
        raise SourceTooLarge(
            f"{source.name} holds more than {MAX_TOTAL_BYTES} bytes of readable text"
        )
