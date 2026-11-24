from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import Any

from labpilot.agent import Bug, Difference
from labpilot.api.errors import ArtifactsTooLargeToCompare
from labpilot.api.finding_lines import prior_text
from labpilot.ingest import Chunk
from labpilot.prompts import (
    PROMPT_BUDGET,
    build_chat_prompt,
    build_prompt,
    instructions_for,
    question_with_reply,
    reserve,
)
from labpilot.retrieval import select
from labpilot.tokens import estimate_tokens

# The lines of what was already found get at most this share of the prompt's
# budget. On 2026-10-25 48 check lines and 33 code lines, with the instruction
# and the outline, came to more than a 12,000-token budget, and the answer was
# refused with ArtifactsTooLargeToCompare. The lines that tell the most are kept.
PRIOR_SHARE = 0.25
PRIOR_LIMIT = int(PROMPT_BUDGET * PRIOR_SHARE)
# What the block around the finding lines adds to the prompt (its title and
# the blank lines), kept free when the lines are fitted into the room left.
PRIOR_LABEL_TOKENS = 200


def _first(evidence: Sequence[Chunk], chunks: tuple[Chunk, ...]) -> tuple[Chunk, ...]:
    # The order for the cut for room only. The ids stay on `chunks`.
    picked: dict[tuple[str, int], Chunk] = {}
    for chunk in (*evidence, *chunks):
        picked.setdefault((chunk.artifact_id, chunk.chunk_index), chunk)
    return tuple(picked.values())


def build_answer_prompt(
    chunks: tuple[Chunk, ...],
    *,
    question: str,
    files: int,
    totals: dict[str, int] | None = None,
    summaries: Mapping[str, str] | None = None,
    last_answer: str = "",
    differences: Sequence[Difference] = (),
    bugs: Sequence[Bug] = (),
    evidence: Sequence[Chunk] = (),
    reference: bool = False,
    user_reply: str = "",
) -> tuple[str, tuple[Chunk, ...]]:
    # What the person said when they were asked (D109) rides with the question,
    # which is the last thing the model reads, behind a note that says whose it is.
    question = question_with_reply(question, user_reply)
    if files == 0:
        return build_chat_prompt(question, last_answer), ()

    # `reference` is True when the only file is A: it is explained, not checked.
    instructions = instructions_for(files, reference=reference)
    # The findings ride in the block that already carries what an earlier pass
    # found, so `build_prompt` and `reserve` both count them.
    common = {
        "question": question,
        "instructions": instructions,
        "summaries": summaries,
        "last_answer": last_answer,
    }
    findings = partial(prior_text, differences, bugs)
    if totals is None:
        prompt = _whole_prompt(chunks, findings, common)
        if estimate_tokens(prompt) <= PROMPT_BUDGET:
            return prompt, chunks

    order, chunks = _evidence_first(evidence, chunks)
    return _fitted_prompt(
        order, chunks, findings(PRIOR_LIMIT), common, totals=totals, files=files
    )


def _whole_prompt(
    chunks: tuple[Chunk, ...], findings: Callable[[int], str], common: dict[str, Any]
) -> str:
    """The prompt with every part, when everything was read.

    Going through `reserve` first would charge the outline as if nothing were
    sent - the long list with a row for every part - and then drop real parts
    that `fits_whole` had just promised would fit. With every part included the
    outline is only a short list of files.

    THE PARTS COME FIRST: the lines of what was found get only the room the parts
    leave. On 2026-10-24 the findings of a stuffed run (F5) cut B from 82 parts
    to 65; the code is the evidence, a finding line is a hint about it.
    """
    bare = build_prompt(chunks, chunks, **common)
    room = PROMPT_BUDGET - estimate_tokens(bare) - PRIOR_LABEL_TOKENS
    limit = min(PRIOR_LIMIT, room)
    prior = findings(limit) if limit > 0 else ""
    return build_prompt(chunks, chunks, prior=prior, **common)


def _evidence_first(
    evidence: Sequence[Chunk], chunks: tuple[Chunk, ...]
) -> tuple[tuple[Chunk, ...], tuple[Chunk, ...]]:
    """(the order for the cut, the list the ids are counted on).

    The parts behind the findings go FIRST on their side, so the cut for room
    drops a search hit before the code a finding is about (R20). The selector
    keeps the order it is given. The IDS stay on `chunks` with any missing
    deciding part at the end (`respond` saves that same list), or the page would
    resolve every citation against a list numbered differently.
    """
    if not evidence:
        return chunks, chunks
    order = _first(evidence, chunks)
    held = {(chunk.artifact_id, chunk.chunk_index) for chunk in chunks}
    missing = (c for c in order if (c.artifact_id, c.chunk_index) not in held)
    return order, (*chunks, *missing)


def _fitted_prompt(
    order: tuple[Chunk, ...],
    chunks: tuple[Chunk, ...],
    prior: str,
    common: dict[str, Any],
    *,
    totals: dict[str, int] | None,
    files: int,
) -> tuple[str, tuple[Chunk, ...]]:
    """The prompt with the parts that fit the budget, in `order`."""
    overhead = reserve(chunks, prior=prior, **common)
    room = PROMPT_BUDGET - overhead
    selected = select(order, budget=room) if room > 0 else ()
    prompt = build_prompt(chunks, selected, prior=prior, totals=totals, **common)

    if not selected or estimate_tokens(prompt) > PROMPT_BUDGET:
        verb = "compare" if files == 2 else "read"
        raise ArtifactsTooLargeToCompare(
            f"too large to {verb}: {len(chunks)} parts need {overhead} tokens "
            f"just to list, of a {PROMPT_BUDGET} token budget, so no part of "
            f"the text fits"
        )

    return prompt, selected
