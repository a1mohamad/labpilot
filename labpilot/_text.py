from __future__ import annotations

ERROR_BODY_CHARS = 300


def truncate(text: str, limit: int = ERROR_BODY_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit]}…"
