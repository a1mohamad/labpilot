import logging
from dataclasses import replace

from labpilot.agent.plan import Plan, Query
from labpilot.ingest import Side

logger = logging.getLogger(__name__)

MAX_QUERIES = 6
# The question the planner may ask the person (D109): short, but it may use two
# lines. Longer than this it is dropped (it is shown on the page and goes into
# the next prompt).
MAX_ASK_CHARS = 400

# Only steps that a node really runs (R18). There is no extract_outcomes step
# (D108). The summaries run on every message whatever the plan says, so
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


def repeats_with_question(ask: str, question: str) -> bool:
    return bool(ask) and ask.strip().lower() == question.strip().lower()


def ask_problem(ask: str) -> str | None:
    if len(ask) > MAX_ASK_CHARS:
        return (
            f"the question for the user is {len(ask)} characters long,"
            f"over the {MAX_ASK_CHARS}"
        )

    return None


def problem_with(plan: Plan, sides: tuple[Side, ...], question: str = "") -> str | None:
    # Only a question that repeats the person's own is worth another try (D109).
    # A long question is dropped by check_plan, and the plan stays.
    if repeats_with_question(plan.ask, question):
        return "the question for the user only repeats the user's own question"
    if plan.about not in ("A", "B", "both"):
        return f"'about' is {plan.about!r}, it must be A, B or both"
    if plan.about in ("A", "B") and plan.about not in sides:
        return f"the question is about side {plan.about!r}, which has no file"
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


def focus(plan: Plan, sides: tuple[Side, ...]) -> Plan:
    """Cut a good plan down to what the question needs (D105, D107)."""
    if not plan.files:
        return replace(plan, steps=(), queries=(), fresh=False)
    if len(sides) == 2 and plan.about in sides:
        dropped = {"find_differences"}
        if plan.about == "A":
            dropped.add("find_bugs")
        return replace(
            plan,
            steps=tuple(step for step in plan.steps if step not in dropped),
            queries=tuple(q for q in plan.queries if q.side == plan.about),
            fresh=plan.fresh and plan.about == "B",
        )
    return plan


def check_plan(plan: Plan, question: str, sides: tuple[Side, ...]) -> Plan:
    # A bad or useless question for the user must not cost the whole plan: the
    # plan is dropped only for its steps and queries.
    if plan.ask and (
        ask_problem(plan.ask) is not None or repeats_with_question(plan.ask, question)
    ):
        plan = replace(plan, ask="")
    # With one file "about" has no meaning, so it is "both" (the safe side).
    if len(sides) < 2 and plan.about != "both":
        plan = replace(plan, about="both")
    problem = problem_with(plan, sides, question)
    if problem is None:
        return focus(plan, sides)
    logger.warning("the plan was rejected, the default plan runs: %s", problem)
    return default_plan(question, sides)
