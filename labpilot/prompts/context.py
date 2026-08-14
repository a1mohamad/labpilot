from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids

SIDES = ("A", "B")
INCLUDED = "text included"
DROPPED = "text NOT included"
NOTHING_SENT = "(no part of this side was included)"


def build_context(chunks: tuple[Chunk, ...], selected: tuple[Chunk, ...]) -> str:
    ids = assign_ids(chunks)
    kept = set(selected)

    unknown = kept - set(ids.values())
    if unknown:
        raise ValueError(f"{len(unknown)} selected chunks are not in chunks")

    parts = []
    for side in SIDES:
        on_side = [(name, chunk) for name, chunk in ids.items() if chunk.side == side]
        if not on_side:
            continue
        parts.append(
            f"SIDE {side}\n\n{_outline(on_side, kept)}\n\n{_text(on_side, kept)}"
        )

    return "\n\n\n".join(parts)


def _outline(on_side: list[tuple[str, Chunk]], kept: set[Chunk]) -> str:
    rows = "\n".join(
        f"{name}  {INCLUDED if chunk in kept else DROPPED}  {chunk.header}"
        for name, chunk in on_side
    )
    return f"ALL PARTS, IN ORDER\n{rows}"


def _text(on_side: list[tuple[str, Chunk]], kept: set[Chunk]) -> str:
    blocks = "\n\n".join(
        f"{name}  {chunk.header}\n{chunk.text}"
        for name, chunk in on_side
        if chunk in kept
    )
    return f"TEXT\n{blocks or NOTHING_SENT}"
