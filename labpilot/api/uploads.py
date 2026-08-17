from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from labpilot.api.config import ApiConfig
from labpilot.api.contracts import Artifact
from labpilot.api.errors import UnnamedUpload, UnreadableUpload, UploadTooLarge


def read_artifact(upload: UploadFile, *, field: str) -> Artifact:
    name = Path(upload.filename or "").name
    if not Path(name).suffix:
        raise UnnamedUpload(
            f"{field} needs a filename with an extension: the extension "
            f"chooses the splitter, and without one the file is cut blindly"
        )

    raw = _read_within_limit(upload, field=field, name=name)

    try:
        return Artifact(name=name, text=raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise UnreadableUpload(f"{field} ({name}) is not UTF-8 text") from exc


def _read_within_limit(upload: UploadFile, *, field: str, name: str) -> bytes:
    # Starlette knows the size once parsing finishes, so the declared size is
    # checked before the bytes are materialised. The post-read check stays as a
    # backstop for the case where size is None.
    if upload.size is not None and upload.size > ApiConfig.MAX_UPLOAD_BYTES:
        raise _too_large(field, name, upload.size)

    raw = upload.file.read()
    if len(raw) > ApiConfig.MAX_UPLOAD_BYTES:
        raise _too_large(field, name, len(raw))

    return raw


def _too_large(field: str, name: str, size: int) -> UploadTooLarge:
    return UploadTooLarge(
        f"{field} ({name}) is {size} bytes, over the "
        f"{ApiConfig.MAX_UPLOAD_BYTES} byte limit"
    )
