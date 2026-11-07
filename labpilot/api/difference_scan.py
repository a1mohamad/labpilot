from functools import partial

from labpilot.agent import (
    SCAN_TOOL_NAME,
    Difference,
    DifferencesError,
    read_scan,
    scan_schema,
)
from labpilot.api.file_parts import FileParts
from labpilot.api.tool_calls import ask_tool, at_once
from labpilot.llm import LLMClient, Tool
from labpilot.prompts import SCAN_GROUP_TOKENS, SCAN_MAX_TOKENS, build_scan_prompt

SCAN_TOOL = Tool(
    name=SCAN_TOOL_NAME,
    description="List what B does that A never says.",
    parameters=scan_schema(),
)


def run_scan(
    client: LLMClient, reference: str, b: FileParts
) -> tuple[list[Difference], bool]:
    """B read in small groups beside what A states: what B does that A never
    says, and whether any call answered.

    `reference` is A's own text when A is small, else A's facts as lines.
    """

    def one(group: FileParts) -> tuple[Difference, ...] | None:
        return ask_tool(
            client,
            build_scan_prompt(reference, group.texts),
            tool=SCAN_TOOL,
            max_tokens=SCAN_MAX_TOKENS,
            read=partial(read_scan, sources=group.sources, texts=group.texts),
            errors=(DifferencesError,),
        )

    answers = [
        answer
        for answer in at_once(one, b.groups(SCAN_GROUP_TOKENS))
        if answer is not None
    ]
    return [item for answer in answers for item in answer], bool(answers)
