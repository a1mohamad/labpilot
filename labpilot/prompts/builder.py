from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.prompts.context import build_context
from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens


def build_prompt(
    chunks: tuple[Chunk, ...],
    selected: tuple[Chunk, ...],
    *,
    question: str,
    instructions: Instructions,
) -> str:
    if not question.strip():
        raise ValueError("Question must not be empty")

    ending = f"{instructions.header}\n\nQuestion: {question}"
    context = build_context(chunks, selected)

    return "\n\n\n".join(instructions.header, context, ending)


def reserve(
    chunks: tuple[Chunk, ...], *, question: str, instructions: Instructions
) -> int:
    empty = build_prompt(chunks, (), question=question, instructions=instructions)
    return estimate_tokens(empty)
