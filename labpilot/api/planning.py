from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import partial

import psycopg

from labpilot.agent import (
    MAX_QUERIES,
    PLAN_TOOL_NAME,
    Plan,
    PlanError,
    allowed_steps,
    default_plan,
    plan_schema,
    present_sides,
    problem_with,
    read_plan,
)
from labpilot.api.errors import UnknownArtifactId
from labpilot.ingest import Side
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.prompts import (
    OPENING_CHARS,
    PLANNER_MAX_TOKENS,
    PLANNER_VERSION,
    build_map,
    build_planner_prompt,
    map_budget,
)
from labpilot.store import UnknownArtifact, read_headers
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "Choose the steps LabPilot runs and what to search for."


def _plan_problem(result: LLMResult, *, sides: tuple[Side, ...]) -> str | None:
    if result.arguments is None:
        return "no arguments"
    try:
        made = read_plan(result.arguments)
    except PlanError as exc:
        return str(exc)
    return problem_with(made, sides)


def make_planner(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str, str, str], Plan]:
    def plan(question: str, a: str, b: str) -> Plan:
        sides = present_sides(a, b)
        if not sides:
            return default_plan(question, sides)

        ids = {"A": a, "B": b}
        try:
            parts = {
                side: read_headers(conn, ids[side], opening_chars=OPENING_CHARS)
                for side in sides
            }
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc

        steps = allowed_steps(sides)
        tool = Tool(
            name=PLAN_TOOL_NAME,
            description=TOOL_DESCRIPTION,
            parameters=plan_schema(sides),
        )

        # The map gets what is left of the tightest tier's input limit after
        # everything else is paid. The schema is counted twice: it travels in
        # `tools` and again in the JSON instruction that complete() adds.
        without_map = build_planner_prompt(question, "", steps, max_queries=MAX_QUERIES)
        fixed = estimate_tokens(without_map) + 2 * estimate_tokens(
            json.dumps(tool.parameters)
        )
        corpus_map = build_map(parts, budget=map_budget(fixed))
        prompt = build_planner_prompt(
            question, corpus_map, steps, max_queries=MAX_QUERIES
        )

        try:
            result = client.generate(
                prompt,
                max_tokens=PLANNER_MAX_TOKENS,
                tool=tool,
                problem_with=partial(_plan_problem, sides=sides),
            )
        except AllFreeTiersExhausted as exc:
            raise PlanError(
                f"no tier gave a good plan ({len(exc.attempts)} attempts)"
            ) from exc
        if result.arguments is None:
            raise PlanError(f"{result.model} gave no arguments")

        made = read_plan(result.arguments)
        logger.info(
            "plan v%d made by %s (tier %d): steps=%s, %d queries",
            PLANNER_VERSION,
            result.model,
            result.tier,
            list(made.steps),
            len(made.queries),
        )
        return made

    return plan
