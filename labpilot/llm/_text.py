from __future__ import annotations

from labpilot.llm.defaults import ERROR_BODY_CHARS


def truncate(text: str, limit: int = ERROR_BODY_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit]}…"