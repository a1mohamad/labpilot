import operator
from typing import Annotated, Any, TypedDict

from labpilot.ingest import Chunk

Chunks = tuple[Chunk, ...]
Totals = dict[str, int] | None


class State(TypedDict):
    question: str
    a: str
    b: str
    history: Annotated[list[str], operator.add]
    summary_a: str
    summary_b: str
    sides: Any
    fits: bool
    chunks: Chunks
    totals: Totals
    prompt: str
    selected: Chunks
    result: Any
