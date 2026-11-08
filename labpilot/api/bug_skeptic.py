import ast
import logging
import re
import textwrap
from collections.abc import Sequence

from labpilot.agent import (
    SKEPTIC_TOOL_NAME,
    Bug,
    judged_bug,
    read_verdicts,
    skeptic_schema,
)
from labpilot.api.file_parts import FileParts
from labpilot.api.tool_calls import ask_tool, at_once
from labpilot.llm import LLMClient, Tool
from labpilot.prompts import (
    SKEPTIC_BATCH,
    SKEPTIC_MAX_TOKENS,
    SKEPTIC_TOKENS,
    SKEPTIC_VOTES,
    build_skeptic_prompt,
)

logger = logging.getLogger(__name__)

SKEPTIC_TOOL = Tool(
    name=SKEPTIC_TOOL_NAME,
    description="Judge every suspect.",
    parameters=skeptic_schema(),
)

_SYNTAX = re.compile(
    r"syntax ?error|does not compile|won't compile|invalid syntax", re.I
)


def parses(bug: Bug) -> bool:
    """True when the suspect says "syntax error" and its Python part parses.

    A claim the code can check itself: the same false "two else blocks" bug was
    judged "real" in all three runs of 2026-11-02. A part that cannot be parsed
    alone (a piece of a longer function) proves nothing, so it stays.
    """
    chunk = bug.evidence
    if (
        chunk is None
        or not chunk.source.endswith(".py")
        or not _SYNTAX.search(bug.text)
    ):
        return False
    try:
        ast.parse(textwrap.dedent(chunk.text))
    except SyntaxError:
        return False
    return True


def _suspect_line(bug: Bug) -> str:
    return f"[{bug.kind}] {bug.text} (quote: {bug.quote[:160]})"


def _context(parts: FileParts, suspects: Sequence[Bug]) -> FileParts:
    # The skeptic reads the whole file when it is small, else only the parts
    # the suspects point at, in their order.
    if parts.tokens <= SKEPTIC_TOKENS:
        return parts
    seen = {bug.evidence.chunk_index for bug in suspects if bug.evidence}
    return parts.only(lambda chunk: chunk.chunk_index in seen)


def judge_suspects(
    parts: FileParts, suspects: Sequence[Bug], client: LLMClient
) -> tuple[Bug, ...]:
    """The suspects the skeptic keeps, each with its label (D87, D92).

    Every batch is judged SKEPTIC_VOTES times at the same time; a suspect needs
    every vote to throw it out.
    """
    if not suspects:
        return ()
    context = _context(parts, suspects).texts
    batches = [
        list(suspects[i : i + SKEPTIC_BATCH])
        for i in range(0, len(suspects), SKEPTIC_BATCH)
    ]

    def vote(job: tuple[int, int]):
        batch = batches[job[0]]
        got = ask_tool(
            client,
            build_skeptic_prompt(context, [_suspect_line(bug) for bug in batch]),
            tool=SKEPTIC_TOOL,
            max_tokens=SKEPTIC_MAX_TOKENS,
            read=lambda arguments: read_verdicts(arguments, len(batch)),
            errors=(),
        )
        return got or [None] * len(batch)

    jobs = [(b, n) for b in range(len(batches)) for n in range(SKEPTIC_VOTES)]
    votes = at_once(vote, jobs)
    kept: list[Bug] = []
    for b, batch in enumerate(batches):
        mine = [votes[i] for i, (vb, _) in enumerate(jobs) if vb == b]
        for position, bug in enumerate(batch):
            labelled = judged_bug(bug, [answer[position] for answer in mine])
            if labelled is not None:
                kept.append(labelled)
    logger.info(
        "bugs: %d suspects, %d kept after %d votes",
        len(suspects),
        len(kept),
        SKEPTIC_VOTES,
    )
    return tuple(kept)
