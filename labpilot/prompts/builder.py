from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids
from labpilot.prompts.context import build_context
from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens

REPORT_MAX_TOKENS = 32_000
PROMPT_BUDGET = 26_000


PRIOR_HEADING = "ALREADY FOUND IN SIDE B"


def build_prompt(
    chunks: tuple[Chunk, ...],
    selected: tuple[Chunk, ...],
    *,
    question: str,
    instructions: Instructions,
    prior: str = "",
) -> str:
    if not question.strip():
        raise ValueError("question must not be empty")

    ending = f"{instructions.closing}\n\nQUESTION: {question.strip()}"
    blocks = [instructions.header, build_context(chunks, selected)]
    if prior.strip():
        blocks.append(f"{PRIOR_HEADING}\n\n{prior.strip()}")
    blocks.append(ending)

    return "\n\n\n".join(blocks)


def reserve(
    chunks: tuple[Chunk, ...],
    *,
    question: str,
    instructions: Instructions,
    prior: str = "",
) -> int:
    empty = build_prompt(
        chunks, (), question=question, instructions=instructions, prior=prior
    )
    prefixes = sum(estimate_tokens(f"{name}  ") for name in assign_ids(chunks))

    return estimate_tokens(empty) + prefixes
