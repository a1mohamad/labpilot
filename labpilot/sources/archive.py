from __future__ import annotations

import tempfile
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath

from labpilot.sources.contracts import Source
from labpilot.sources.defaults import (
    COPY_CHUNK_BYTES,
    MAX_ARCHIVE_BYTES,
    MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
)
from labpilot.sources.errors import SourceNotFound, SourceTooLarge, UnsafeArchive


@contextmanager
def open_zip(path: str | Path, *, name: str | None = None) -> Generator[Source]:
    archive = Path(path)
    if not archive.is_file():
        raise SourceNotFound(f"{archive} is not a file")

    size = archive.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise SourceTooLarge(
            f"{archive.name} is {size} bytes, over the {MAX_ARCHIVE_BYTES} limit"
        )

    with tempfile.TemporaryDirectory(
        prefix="labpilot-", ignore_cleanup_errors=True
    ) as temporary:
        root = Path(temporary)
        try:
            with zipfile.ZipFile(archive) as bundle:
                _refuse_suspicious_members(bundle)
                _extract(bundle, root)
        except zipfile.BadZipFile as exc:
            raise UnsafeArchive(f"{archive.name} is not a readable zip file") from exc

        yield Source(name=name or archive.stem, root=root)


def _refuse_suspicious_members(bundle: zipfile.ZipFile) -> None:
    members = bundle.infolist()

    if len(members) > MAX_FILES:
        raise SourceTooLarge(f"the archive holds more than {MAX_FILES} entries")

    unsafe = [member.filename for member in members if _is_unsafe(member.filename)]
    if unsafe:
        raise UnsafeArchive(f"the archive holds unsafe paths: {unsafe[:3]}")

    declared = sum(member.file_size for member in members)
    if declared > MAX_UNCOMPRESSED_BYTES:
        raise SourceTooLarge(
            f"the archive declares {declared} bytes once unpacked, over the "
            f"{MAX_UNCOMPRESSED_BYTES} limit"
        )


def _is_unsafe(name: str) -> bool:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    return (
        pure.is_absolute()
        or ".." in pure.parts
        or PureWindowsPath(normalized).drive != ""
    )


def _extract(bundle: zipfile.ZipFile, root: Path) -> None:
    written = 0
    for member in bundle.infolist():
        if member.is_dir():
            continue

        target = root / member.filename
        target.parent.mkdir(parents=True, exist_ok=True)

        with bundle.open(member) as packed, target.open("wb") as unpacked:
            while chunk := packed.read(COPY_CHUNK_BYTES):
                written += len(chunk)
                if written > MAX_UNCOMPRESSED_BYTES:
                    raise SourceTooLarge(
                        f"the archive unpacked past {MAX_UNCOMPRESSED_BYTES} bytes"
                    )
                unpacked.write(chunk)
