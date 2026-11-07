from collections.abc import Callable, Mapping, Sequence
from functools import partial
from itertools import product

from labpilot.agent import (
    JUDGE_TOOL_NAME,
    MERGE_TOOL_NAME,
    Difference,
    DifferencesError,
    judge_schema,
    judged_findings,
    merge_schema,
    read_judge,
    read_merge,
)
from labpilot.api.file_parts import FileParts
from labpilot.api.tool_calls import ask_tool, at_once
from labpilot.llm import LLMClient, Tool
from labpilot.prompts import (
    JUDGE_BATCH,
    JUDGE_MAX_TOKENS,
    JUDGE_VOTES,
    MERGE_MAX_TOKENS,
    build_judge_prompt,
    build_merge_prompt,
)

JUDGE_TOOL = Tool(
    name=JUDGE_TOOL_NAME,
    description="Judge every finding.",
    parameters=judge_schema(),
)
MERGE_TOOL = Tool(
    name=MERGE_TOOL_NAME,
    description="Group the findings that make the same point.",
    parameters=merge_schema(),
)

# A finding is shown to the merge cut at this length: the point, not every
# detail.
MERGE_LINE_CHARS = 300

Merge = Callable[[Mapping[int, str]], list[list[int]]]


def finding_line(found: Difference) -> str:
    fact = f'A states: "{found.fact}". ' if found.fact else ""
    return f'{fact}{found.text} ({found.source}): "{found.quote}"'


def judge(
    client: LLMClient,
    findings: Sequence[Difference],
    b: FileParts,
    reference: str,
) -> list[Difference]:
    """The findings the judges keep (see `judged_findings` for the rules).

    The findings are judged in batches of JUDGE_BATCH, each batch JUDGE_VOTES
    times, all at the same time. A batch numbers its findings from where it
    starts, so the answers of all batches fit one list.
    """
    lines = [finding_line(found) for found in findings]
    read = partial(read_judge, count=len(findings))

    def one(job: tuple[int, int]):
        _, first = job
        return ask_tool(
            client,
            build_judge_prompt(
                lines[first : first + JUDGE_BATCH], first, b.texts, reference
            ),
            tool=JUDGE_TOOL,
            max_tokens=JUDGE_MAX_TOKENS,
            read=read,
            errors=(DifferencesError,),
        )

    jobs = list(product(range(JUDGE_VOTES), range(0, len(lines), JUDGE_BATCH)))
    votes: dict[int, list[tuple[str, str]]] = {}
    for answer in at_once(one, jobs):
        for n, (verdict, relation, _) in (answer or {}).items():
            votes.setdefault(n, []).append((verdict, relation))
    return judged_findings(findings, votes)


def make_merger(*clients: LLMClient) -> Merge:
    """A merge that asks each client in turn until one answers.

    With no answer there are no groups, so nothing is hidden: a repeat costs a
    line, a wrong merge would cost a finding.
    """

    def merge(findings: Mapping[int, str]) -> list[list[int]]:
        if len(findings) < 2:
            return []
        shown = {n: line[:MERGE_LINE_CHARS] for n, line in findings.items()}
        read = partial(read_merge, allowed=list(shown))
        for client in clients:
            groups = ask_tool(
                client,
                build_merge_prompt(shown),
                tool=MERGE_TOOL,
                max_tokens=MERGE_MAX_TOKENS,
                read=read,
                errors=(DifferencesError,),
            )
            if groups is not None:
                return groups
        return []

    return merge
