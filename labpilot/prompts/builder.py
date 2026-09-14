from __future__ import annotations

from labpilot.ingest import Chunk
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
    # The empty prompt already carries the WHOLE outline, because build_prompt
    # renders it with nothing selected - so the outline is counted exactly, at
    # whatever level of the ladder it chose.
    #
    # What is deliberately NOT added is an id prefix per chunk. That term used
    # to sit here, charging `B-1234  ` for every chunk in the corpus though
    # only the SELECTED handful is ever printed in the TEXT block. It was
    # always an over-estimate; the per-chunk outline merely hid it. Measured
    # 2026-09-14 on an 8,333-chunk upload once the outline went per file:
    #
    #     outline      26 tokens
    #     prefixes 24,899 tokens   <- 96% of a 26,000 budget, for names
    #                                 that would never be rendered
    #
    # so it let 4 chunks through instead of hundreds, and the outline fix
    # would have bought almost nothing. The real per-chunk overhead is about 3
    # tokens on a chunk of ~350, and it belongs in the SELECTOR, which charges
    # per chunk as it packs - that is step 3's rewrite. Until then the small
    # under-estimate is caught by the caller's own check that the finished
    # prompt fits.
    empty = build_prompt(
        chunks, (), question=question, instructions=instructions, prior=prior
    )

    return estimate_tokens(empty)
