from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.tokens import estimate_tokens

INPUT_BUDGET = 20000


def select(chunks: tuple[Chunk], *, budget: int = INPUT_BUDGET) -> tuple[Chunk]:
    per_side = budget // 2
    picked: list[Chunk] = []
    for side in ("A", "B"):
        spent = 0
        for chunk in chunks:
            if chunk.side != side:
                continue
            cost = estimate_tokens(chunk.embed_text)
            if cost + spent > per_side:
                break
            picked.append(chunk)
            spent += cost
    return tuple(picked)
