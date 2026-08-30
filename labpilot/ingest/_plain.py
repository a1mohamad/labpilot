from __future__ import annotations

from labpilot.ingest.errors import NotUtf8Text


def load_text(raw: bytes) -> str:
    # utf-8-sig strips a leading byte-order mark and behaves exactly like
    # utf-8 when there is none. A BOM left in place makes ast.parse fail,
    # which drops a Python file to the recursive splitter with nothing raised.
    try:
        raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise NotUtf8Text(f"not UTF-8 text: {exc}") from exc
