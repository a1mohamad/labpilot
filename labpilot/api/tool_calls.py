import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.timing import in_this_context

logger = logging.getLogger(__name__)

# The calls of one step are made at the same time, at most this many at once.
CALLS_AT_ONCE = 4

Answer = TypeVar("Answer")
Job = TypeVar("Job")


def ask_tool(
    client: LLMClient,
    prompt: str,
    *,
    tool: Tool,
    max_tokens: int,
    read: Callable[[dict[str, object]], Answer],
    errors: tuple[type[Exception], ...],
) -> Answer | None:
    """The tier's answer, read by `read`, or None when no tier gave one that reads.

    `read` raises one of `errors` when the answer is wrong. Then the next tier
    is asked (D50), so a wrong answer costs one more call and never the step.
    """

    def problem(result: LLMResult) -> str | None:
        if result.arguments is None:
            return "the answer has no arguments"
        try:
            read(result.arguments)
        except errors as exc:
            return str(exc)
        return None

    try:
        result = client.generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem
        )
    except AllFreeTiersExhausted as exc:
        logger.warning("no tier answered %s (%d tried)", tool.name, len(exc.attempts))
        return None
    if result.arguments is None:
        return None
    try:
        answer = read(result.arguments)
    except errors:
        return None
    logger.info("%s answered by %s (tier %s)", tool.name, result.model, result.tier)
    return answer


def at_once(
    work: Callable[[Job], Answer], jobs: Sequence[Job], limit: int = CALLS_AT_ONCE
) -> list[Answer]:
    """`work` for every job, at most `limit` at the same time, in job order."""
    if not jobs:
        return []
    with ThreadPoolExecutor(min(len(jobs), limit)) as pool:
        return list(pool.map(in_this_context(work), jobs))
