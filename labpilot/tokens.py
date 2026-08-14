from __future__ import annotations

import math

CHARS_PER_TOKEN = 3


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)
