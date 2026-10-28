import operator
from typing import Annotated, Any, TypedDict

from labpilot.agent.claim import Claim
from labpilot.agent.code_finding import CodeFinding
from labpilot.agent.finding import Finding
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
    findings: Annotated[list[Finding], operator.add]
    code_findings: Annotated[list[CodeFinding], operator.add]
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
