from __future__ import annotations

from labpilot.api.errors import (
    ArtifactsTooLargeToCompare,
)
from labpilot.ingest import (
    Chunk,
)
from labpilot.prompts import (
    PROMPT_BUDGET,
    REPORT,
    build_prompt,
    reserve,
)
from labpilot.retrieval import select
from labpilot.tokens import estimate_tokens


def build_report_prompt(
    chunks: tuple[Chunk, ...],
    *,
    question: str,
    totals: dict[str, int] | None = None,
) -> tuple[str, tuple[Chunk, ...]]:
    overhead = reserve(chunks, question=question, instructions=REPORT)
    room = PROMPT_BUDGET - overhead
    selected = select(chunks, budget=room) if room > 0 else ()
    prompt = build_prompt(
        chunks,
        selected,
        question=question,
        instructions=REPORT,
        totals=totals,
    )

    if not selected or estimate_tokens(prompt) > PROMPT_BUDGET:
        raise ArtifactsTooLargeToCompare(
            f"too large to compare: {len(chunks)} parts need {overhead} tokens "
            f"just to list, of a {PROMPT_BUDGET} token budget, so no artifact "
            f"text fits. Step 0 sends one outline line per part; use smaller "
            f"artifacts until Step 1 replaces it with a per-file outline"
        )

    return prompt, selected
