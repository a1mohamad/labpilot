from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids
from labpilot.prompts.context import build_context
from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens

REPORT_MAX_TOKENS = 16_000
PROMPT_BUDGET = 26_000


def build_prompt(
    chunks: tuple[Chunk, ...],
    selected: tuple[Chunk, ...],
    *,
    question: str,
    instructions: Instructions,
) -> str:
    if not question.strip():
        raise ValueError("question must not be empty")

    ending = f"{instructions.closing}\n\nQUESTION: {question.strip()}"

    return "\n\n\n".join((instructions.header, build_context(chunks, selected), ending))


def reserve(
    chunks: tuple[Chunk, ...], *, question: str, instructions: Instructions
) -> int:
    empty = build_prompt(chunks, (), question=question, instructions=instructions)
    prefixes = sum(estimate_tokens(f"{name}  ") for name in assign_ids(chunks))

    return estimate_tokens(empty) + prefixes
