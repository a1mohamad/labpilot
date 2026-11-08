import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from labpilot.agent import (
    BUGS_TOOL_NAME,
    CHECKLIST_AUDIT_TOOL_NAME,
    CHECKLIST_TOOL_NAME,
    Bug,
    BugsError,
    bugs_schema,
    checklist_audit_schema,
    checklist_schema,
    merge_obligations,
    read_bugs,
    read_checklist,
    read_checklist_audit,
)
from labpilot.api.file_parts import FileParts
from labpilot.api.tool_calls import CALLS_AT_ONCE, ask_tool
from labpilot.llm import LLMClient, Tool
from labpilot.prompts import (
    BUGS_MAX_TOKENS,
    CHECKLIST_AUDIT_MAX_TOKENS,
    CHECKLIST_MAX_TOKENS,
    CHECKLISTS,
    HUNTS,
    WHOLE_GROUP_TOKENS,
    Hunt,
    Instructions,
    build_checklist_audit_prompt,
    build_checklist_prompt,
    build_hunt_prompt,
)

logger = logging.getLogger(__name__)

HUNT_TOOL = Tool(
    name=BUGS_TOOL_NAME,
    description="List the real defects of the work.",
    parameters=bugs_schema(),
)
CHECKLIST_TOOL = Tool(
    name=CHECKLIST_TOOL_NAME,
    description="List the obligations an expert checks.",
    parameters=checklist_schema(),
)
CHECKLIST_AUDIT_TOOL = Tool(
    name=CHECKLIST_AUDIT_TOOL_NAME,
    description="Answer every obligation of the checklist.",
    parameters=checklist_audit_schema(),
)


def _hunt(
    client: LLMClient, hunt: Hunt, group: FileParts, summary: str
) -> tuple[Bug, ...] | None:
    read = partial(
        read_bugs, sources=group.sources, texts=group.texts, chunks=group.chunks
    )
    return ask_tool(
        client,
        build_hunt_prompt(
            hunt.instructions, group.texts, summary if hunt.with_summary else ""
        ),
        tool=HUNT_TOOL,
        max_tokens=BUGS_MAX_TOKENS,
        read=read,
        errors=(BugsError,),
    )


def _checklist(
    client: LLMClient, instructions: Instructions, summary: str, parts: FileParts
) -> tuple[str, ...]:
    headers = [chunk.header for chunk in parts.chunks]
    got = ask_tool(
        client,
        build_checklist_prompt(instructions, summary, headers),
        tool=CHECKLIST_TOOL,
        max_tokens=CHECKLIST_MAX_TOKENS,
        read=read_checklist,
        errors=(BugsError,),
    )
    return got or ()


def _audit(
    client: LLMClient, obligations: tuple[str, ...], group: FileParts
) -> tuple[Bug, ...] | None:
    read = partial(
        read_checklist_audit,
        obligations=obligations,
        sources=group.sources,
        texts=group.texts,
        chunks=group.chunks,
    )
    return ask_tool(
        client,
        build_checklist_audit_prompt(obligations, group.texts),
        tool=CHECKLIST_AUDIT_TOOL,
        max_tokens=CHECKLIST_AUDIT_MAX_TOKENS,
        read=read,
        errors=(BugsError,),
    )


def find_suspects(
    parts: FileParts, summary: str, *, client: LLMClient, trace_client: LLMClient
) -> list[Bug]:
    """Every suspect of the three hunts and the checklist audit (D87, D90).

    The checklists are asked first, so the audit does not wait behind the
    hunts: the hunts run while the checklists are written. A small hunt (the
    trace) is many calls on a cheap chain (D93).
    """
    jobs = [
        (hunt, group)
        for hunt in HUNTS
        for group in parts.groups(hunt.group_tokens, by_file=hunt.by_file)
    ]
    with ThreadPoolExecutor(CALLS_AT_ONCE) as pool:
        written = [
            pool.submit(_checklist, client, instructions, summary, parts)
            for instructions in CHECKLISTS
        ]
        hunted = [
            pool.submit(
                _hunt, trace_client if hunt.small else client, hunt, group, summary
            )
            for hunt, group in jobs
        ]
        obligations = merge_obligations([future.result() for future in written])
        audited = [
            pool.submit(_audit, client, obligations, group)
            for group in parts.groups(WHOLE_GROUP_TOKENS, by_file=True)
            if obligations
        ]
        answers = [future.result() for future in hunted + audited]

    given = [answer for answer in answers if answer is not None]
    if not given:
        asked = len(answers) + len(written)
        raise BugsError(f"no tier answered any of {asked} questions")
    logger.info(
        "bugs: %d hunts and %d audits answered, %d obligations",
        len([a for a in answers[: len(hunted)] if a is not None]),
        len([a for a in answers[len(hunted) :] if a is not None]),
        len(obligations),
    )
    return [bug for answer in given for bug in answer]
