from collections.abc import Callable, Sequence
from typing import Any

from langgraph.types import Overwrite

from labpilot.agent.state import Chunks, State, Totals
from labpilot.ingest import Chunk


def merge_chunks(found: Sequence[Chunks]) -> Chunks:
    merged: list[Chunk] = []
    seen: set[tuple[str, int]] = set()
    for rank in range(max(map(len, found), default=0)):
        for chunks in found:
            if rank >= len(chunks):
                continue
            chunk = chunks[rank]
            key = (chunk.artifact_id, chunk.chunk_index)
            if key not in seen:
                seen.add(key)
                merged.append(chunk)

    return tuple(merged)


def make_merge_node(
    totals_of: Callable[[Any], Totals], rank_side: Callable[[str, Chunks], Chunks]
) -> Callable[[State], dict[str, Any]]:
    def merge_node(state: State) -> dict[str, Any]:
        chunks: list[Chunk] = []
        for side in sorted({found[0].side for found in state["found"] if found}):
            lists = [
                found for found in state["found"] if found and found[0].side == side
            ]
            pile = merge_chunks(lists)
            if pile:
                chunks.extend(rank_side(state["question"], pile))

        return {
            "chunks": tuple(chunks),
            "totals": totals_of(state["sides"]),
            "found": Overwrite([]),
        }

    return merge_node
