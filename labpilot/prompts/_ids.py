from __future__ import annotations

from labpilot.ingest import Chunk


def assign_ids(chunks: tuple[Chunk, ...]) -> dict[str, Chunk]:
    counters: dict[str, int] = {}
    assigned: dict[str, Chunk] = {}

    for chunk in chunks:
        index = counters.get(chunk.side, 0)
        counters[chunk.side] = index + 1
        assigned[f"{chunk.side}-{index}"] = chunk

    return assigned
