from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from labpilot.sources.contracts import Source
from labpilot.sources.errors import SourceNotFound


@contextmanager
def open_folder(path: Path | str, *, name: str | None = None) -> Generator[Source]:
    root = Path(path).resolve()
    if not root.is_dir():
        raise SourceNotFound(f"{root} is not a folder")
    yield Source(name=name or root.name, root=root)
