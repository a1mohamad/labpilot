from collections.abc import Sequence
from functools import partial
from itertools import product

from labpilot.agent import (
    AUDIT_TOOL_NAME,
    Difference,
    DifferencesError,
    audit_findings,
    audit_schema,
    read_audit,
)
from labpilot.api.file_parts import FileParts
from labpilot.api.tool_calls import ask_tool, at_once
from labpilot.llm import LLMClient, Tool
from labpilot.prompts import (
    AUDIT_BATCH,
    AUDIT_GROUP_TOKENS,
    AUDIT_MAX_TOKENS,
    AUDIT_VOTES,
    build_audit_prompt,
)

AUDIT_TOOL = Tool(
    name=AUDIT_TOOL_NAME,
    description="Give one verdict for each fact of A.",
    parameters=audit_schema(),
)


def run_audit(
    client: LLMClient, facts: Sequence[str], b: FileParts
) -> tuple[list[Difference], bool]:
    """A's facts checked against B: the facts B breaks, and whether any call
    answered.

    Each call asks up to AUDIT_BATCH facts against one big group of B, and every
    call is made AUDIT_VOTES times. The calls run at the same time.
    """
    numbers = list(range(len(facts)))
    batches = [
        numbers[i : i + AUDIT_BATCH] for i in range(0, len(numbers), AUDIT_BATCH)
    ]
    groups = b.groups(AUDIT_GROUP_TOKENS, by_file=True)

    def one(job: tuple[int, list[int], FileParts]):
        vote, batch, group = job
        read = partial(
            read_audit,
            facts=facts,
            numbers=batch,
            sources=group.sources,
            texts=group.texts,
        )
        got = ask_tool(
            client,
            build_audit_prompt(facts, batch, group.texts),
            tool=AUDIT_TOOL,
            max_tokens=AUDIT_MAX_TOKENS,
            read=read,
            errors=(DifferencesError,),
        )
        return None if got is None else (vote, got)

    jobs = list(product(range(AUDIT_VOTES), batches, groups))
    answers = [answer for answer in at_once(one, jobs) if answer is not None]
    return audit_findings(answers, len(facts)), bool(answers)
