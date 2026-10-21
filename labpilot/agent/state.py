import operator
from typing import Annotated, Any, TypedDict

from labpilot.agent.plan import Plan
from labpilot.ingest import Chunk

Chunks = tuple[Chunk, ...]
Totals = dict[str, int] | None


class State(TypedDict):
    question: str
    a: str
    b: str
    history: Annotated[list[str], operator.add]
    last_asnwer: str
    plan: Plan
    summary_a: str
    summary_b: str
    sides: Any
    fits: bool
    found: Annotated[list[Chunks], operator.add]
    chunks: Chunks
    totals: Totals
    prompt: str
    selected: Chunks
    result: Any
