import logging

from labpilot.agent.plan import Plan, Query
from labpilot.ingest import Side

logger = logging.getLogger(__name__)

MAX_QUERIES = 6

# Only steps that a node really runs (R18). extract_outcomes (slice 10) is not
# built yet. The summaries run on every message whatever the plan says, so
# "summarize" is listed for the planner to read and costs nothing. The claims
# run when find_differences runs, because they give it A's facts. find_bugs
# reads B alone, so it is allowed only when B has a file (D106).
STEPS_BY_FILES: dict[int, tuple[str, ...]] = {
    0: (),
    1: ("summarize", "find_bugs"),
    2: ("summarize", "find_differences", "find_bugs"),
}

# Steps that read side B, so they are dropped when B has no file.
NEEDS_B: tuple[str, ...] = ("find_bugs",)


def present_sides(a: str, b: str) -> tuple[Side, ...]:
    sides: list[Side] = []
    if a:
        sides.append("A")
    if b:
        sides.append("B")

    return tuple(sides)


def allowed_steps(sides: tuple[Side, ...]) -> tuple[str, ...]:
    steps = STEPS_BY_FILES[len(sides)]
    if "B" in sides:
        return steps
    return tuple(step for step in steps if step not in NEEDS_B)


def question_queries(question: str, sides: tuple[Side, ...]) -> tuple[Query, ...]:
    return tuple(Query(side, question) for side in sides)


def default_plan(question: str, sides: tuple[Side, ...]) -> Plan:
    return Plan(
        steps=allowed_steps(sides),
        queries=question_queries(question, sides),
        source="default",
    )


def problem_with(plan: Plan, sides: tuple[Side, ...]) -> str | None:
    allowed = allowed_steps(sides)
    for step in plan.steps:
        if step not in allowed:
            files = ", ".join(sides) or "no file"
            return f"step {step!r} is not allowed with {files}"
    if len(set(plan.steps)) != len(plan.steps):
        return "a step is listed twice"
    if len(plan.queries) > MAX_QUERIES:
        return f"{len(plan.queries)} queries, the limit is {MAX_QUERIES}"
    for query in plan.queries:
        if query.side not in sides:
            return f"a query is for side {query.side!r}, which has no file"
        if not query.text.strip():
            return "a query is blank"

    return None


def check_plan(plan: Plan, question: str, sides: tuple[Side, ...]) -> Plan:
    problem = problem_with(plan, sides)
    if problem is None:
        return plan
    logger.warning("the plan was rejected, the default plan runs: %s", problem)
    return default_plan(question, sides)
