from __future__ import annotations

from collections.abc import Mapping

from labpilot.ingest import Chunk
from labpilot.prompts.context import build_context
from labpilot.prompts.followups import last_answer_block
from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens

REPORT_MAX_TOKENS = 32_000
PROMPT_BUDGET = 30_000


PRIOR_HEADING = "ALREADY FOUND IN SIDE B"
SUMMARIES_NOTE = (
    "SUMMARIES - a short guide, written by a fast model. For a big side it read "
    "only the first parts. The parts below are the evidence: where a summary and "
    "a part disagree, trust the part."
)

# What the prompt carries BESIDES the evidence, the instruction and the
# outline, and that `fits_whole` cannot see because it runs before the prompt
# exists: two summaries of at most 150 words (about 350 estimated tokens each,
# at 3 characters a token) with their note and headings, and the last-answer
# excerpt of at most 2,000 characters (677 tokens). About 1,500 tokens at the
# largest; 2,000 leaves room for the separators and a summary that runs a
# little long. A test builds the largest of each and checks it stays under.
PROMPT_EXTRAS_TOKENS = 2_000


def _summaries_block(summaries: Mapping[str, str] | None) -> str:
    written = [
        f"SUMMARY OF SIDE {side}\n\n{text.strip()}"
        for side, text in sorted((summaries or {}).items())
        if text.strip()
    ]
    return "\n\n".join([SUMMARIES_NOTE, *written]) if written else ""


def build_prompt(
    chunks: tuple[Chunk, ...],
    selected: tuple[Chunk, ...],
    *,
    question: str,
    instructions: Instructions,
    prior: str = "",
    totals: dict[str, int] | None = None,
    summaries: Mapping[str, str] | None = None,
    last_answer: str = "",
) -> str:
    if not question.strip():
        raise ValueError("question must not be empty")

    ending = f"{instructions.closing}\n\nQUESTION: {question.strip()}"
    blocks = [instructions.header]
    if summary_block := _summaries_block(summaries):
        blocks.append(summary_block)
    blocks.append(build_context(chunks, selected, totals=totals))
    if prior.strip():
        blocks.append(f"{PRIOR_HEADING}\n\n{prior.strip()}")
    if answer_block := last_answer_block(last_answer):
        blocks.append(answer_block)
    blocks.append(ending)

    return "\n\n\n".join(blocks)


def reserve(
    chunks: tuple[Chunk, ...],
    *,
    question: str,
    instructions: Instructions,
    prior: str = "",
    summaries: Mapping[str, str] | None = None,
    last_answer: str = "",
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
        chunks,
        (),
        question=question,
        instructions=instructions,
        prior=prior,
        summaries=summaries,
        last_answer=last_answer,
    )

    return estimate_tokens(empty)
