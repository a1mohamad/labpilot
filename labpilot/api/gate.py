import logging
from collections.abc import Callable

from labpilot.agent import (
    GATE_TOOL_NAME,
    Correspondence,
    GateError,
    gate_schema,
    read_correspondence,
)
from labpilot.api.tool_calls import ask_tool
from labpilot.llm import LLMClient, LLMResult, Tool
from labpilot.prompts import GATE_MAX_TOKENS, GATE_VERSION, build_gate_prompt

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "say whether two works correspond."

# No model wrote the text of a halt, and the page shows who answered.
HALT_MODEL = "correspondence gate"


def make_gate(client: LLMClient) -> Callable[[str, str], Correspondence]:
    tool = Tool(
        name=GATE_TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters=gate_schema(),
    )

    def gate(summary_a: str, summary_b: str) -> Correspondence:
        found = ask_tool(
            client,
            build_gate_prompt(summary_a, summary_b),
            tool=tool,
            max_tokens=GATE_MAX_TOKENS,
            read=read_correspondence,
            errors=(GateError,),
        )
        if found is None:
            raise GateError("no tier could judge it")
        logger.info("gate v%d: %s", GATE_VERSION, found.verdict)
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
