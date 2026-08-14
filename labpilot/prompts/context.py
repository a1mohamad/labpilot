from __future__ import annotations

from labpilot.ingest import Chunk

SIDE_TITLES = {
    "A": "SIDE A - the reference",
    "B": "SIDE B - the implementation",
}


def build_context(chunks: tuple[Chunk, ...]) -> str:
    parts = []
    for side in ("A", "B"):
        picked = [chunk for chunk in chunks if chunk.side == side]
        if not picked:
            continue
        body = "\n\n".join(f"{chunk.header}\n{chunk.text}" for chunk in picked)
        parts.append(f"{SIDE_TITLES[side]}\n\n{body}")

    return "\n\n\n".join(parts)
