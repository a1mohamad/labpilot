from __future__ import annotations

import math

from labpilot.llm.defaults import CHARS_PER_TOKEN, ERROR_BODY_CHARS


def truncate(text: str, limit: int = ERROR_BODY_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit]}…"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)
