import logging
from collections.abc import Callable

from labpilot.agent import (
    GATE_TOOL_NAME,
    Correspondence,
    GateError,
    gate_schema,
    read_correspondence,
)
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.prompts import GATE_MAX_TOKENS, GATE_VERSION, build_gate_prompt

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "say whether two works correspond."

# No model wrote the text of a halt, and the page shows who answered.
HALT_MODEL = "correspondence gate"


def _gate_problem(result: LLMResult) -> str | None:
    if result.arguments is None:
        return "no arguments"
    try:
        read_correspondence(result.arguments)
    except GateError as exc:
        return str(exc)
    return None


def make_gate(client: LLMClient) -> Callable[[str, str], Correspondence]:
    tool = Tool(
        name=GATE_TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters=gate_schema(),
    )

    def gate(summary_a: str, summary_b: str) -> Correspondence:
        try:
            result = client.generate(
                build_gate_prompt(summary_a, summary_b),
                max_tokens=GATE_MAX_TOKENS,
                tool=tool,
                problem_with=_gate_problem,
            )
        except AllFreeTiersExhausted as exc:
            raise GateError(f"no tier could judge it ({len(exc.attempts)}") from exc
        if result.arguments is None:
            raise GateError(f"{result.model} gave no arguments")

        found = read_correspondence(result.arguments)
        logger.info(
            "gate v%d by %s (tier %s): %s",
            GATE_VERSION,
            result.model,
            result.tier,
            found.verdict,
        )
        return found

    return gate


def halt_answer(summary_a: str, summary_b: str, reason: str) -> LLMResult:
    """The answer when the gate says NONE: the two summaries and the reason.

    It is a prepared text and no model is called, so a halt costs nothing more.
    """
    text = "\n\n".join(
        [
            "I did not compare these two, because they do not seem to be about "
            "the same work.",
            f"Why: {reason}",
            f"A: {summary_a}",
            f"B: {summary_b}",
            "To go on, add the file you meant to compare, or ask your question "
            "about one of the files alone.",
        ]
    )
    return LLMResult(
        text=text,
        model=HALT_MODEL,
        tier=0,
        finish_reason="stop",
    )
