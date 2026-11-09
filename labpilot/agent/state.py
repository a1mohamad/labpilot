import operator
from typing import Annotated, Any, TypedDict

from labpilot.agent.bug import Bug
from labpilot.agent.claim import Claim
from labpilot.agent.correspondence import Correspondence
from labpilot.agent.difference import Difference
from labpilot.agent.plan import Plan
from labpilot.ingest import Chunk

Chunks = tuple[Chunk, ...]
Totals = dict[str, int] | None


class State(TypedDict):
    question: str
    a: str
    b: str
    history: Annotated[list[str], operator.add]
    last_answer: str
    plan: Plan
    claims: tuple[Claim, ...]
    differences: Annotated[list[Difference], operator.add]
    bugs: Annotated[list[Bug], operator.add]
    summary_a: str
    summary_b: str
    correspondence: Correspondence | None
    sides: Any
    fits: bool
    found: Annotated[list[Chunks], operator.add]
    chunks: Chunks
    totals: Totals
    prompt: str
    selected: Chunks
    result: Any
