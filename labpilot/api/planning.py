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
from labpilot.api.tool_calls import ask_tool
from labpilot.ingest import Side
from labpilot.llm import LLMClient, Tool
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


def _read(
    arguments: dict[str, object], *, sides: tuple[Side, ...], question: str
) -> Plan:
    """The plan of this answer. A plan that does not fit the question is refused."""
    made = read_plan(arguments)
    problem = problem_with(made, sides, question)
    if problem is not None:
        raise PlanError(problem)
    return made


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

        made = ask_tool(
            client,
            prompt,
            tool=tool,
            max_tokens=PLANNER_MAX_TOKENS,
            read=partial(_read, sides=sides, question=question),
            errors=(PlanError,),
        )
        if made is None:
            raise PlanError("no tier gave a good plan")
        logger.info(
            "plan v%d: steps=%s, queries=%s",
            PLANNER_VERSION,
            list(made.steps),
            [f"{query.side}: {query.text}" for query in made.queries],
        )
        return made

    return plan
