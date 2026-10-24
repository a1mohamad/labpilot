import logging

from labpilot.agent.plan import Plan, Query
from labpilot.ingest import Side

logger = logging.getLogger(__name__)

MAX_QUERIES = 6

# Only steps that a node really runs (R18). find_bugs (slice 9) and
# extract_outcomes (slice 10) are not built yet: the planner listed them on
# every run of 2026-10-24 and nothing ran them. The summaries run on every
# message whatever the plan says, so "summarize" is listed for the planner to
# read and costs nothing.
STEPS_BY_FILES: dict[int, tuple[str, ...]] = {
    0: (),
    1: ("summarize",),
    2: ("summarize", "extract_claims", "find_missing"),
}


def present_sides(a: str, b: str) -> tuple[Side, ...]:
    sides: list[Side] = []
    if a:
        sides.append("A")
    if b:
        sides.append("B")

    return tuple(sides)


def allowed_steps(sides: tuple[Side, ...]) -> tuple[str, ...]:
    return STEPS_BY_FILES[len(sides)]


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
            return f"step {step!r} is not allowed with {len(sides)} file(s)"
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
