from __future__ import annotations

from collections.abc import Mapping

from labpilot.api.errors import (
    ArtifactsTooLargeToCompare,
)
from labpilot.ingest import (
    Chunk,
)
from labpilot.prompts import (
    PROMPT_BUDGET,
    build_chat_prompt,
    build_prompt,
    instructions_for,
    reserve,
)
from labpilot.retrieval import select
from labpilot.tokens import estimate_tokens


def build_answer_prompt(
    chunks: tuple[Chunk, ...],
    *,
    question: str,
    files: int,
    totals: dict[str, int] | None = None,
    summaries: Mapping[str, str] | None = None,
    last_answer: str = "",
) -> tuple[str, tuple[Chunk, ...]]:
    if files == 0:
        return build_chat_prompt(chunks, question=question), ()
    instructions = instructions_for(files)
    overhead = reserve(
        chunks,
        question=question,
        instructions=instructions,
        summaries=summaries,
        last_answer=last_answer,
    )
    room = PROMPT_BUDGET - overhead
    selected = select(chunks, budget=room) if room > 0 else ()
    prompt = build_prompt(
        chunks,
        selected,
        question=question,
        instructions=instructions,
        totals=totals,
        summaries=summaries,
        last_answer=last_answer,
    )

    if not selected or estimate_tokens(prompt) > PROMPT_BUDGET:
        verb = "compare" if files == 2 else "read"
        raise ArtifactsTooLargeToCompare(
            f"too large to {verb}: {len(chunks)} parts need {overhead} tokens "
            f"just to list, of a {PROMPT_BUDGET} token budget, so no part of "
            f"the text fits"
        )

    return prompt, selected
