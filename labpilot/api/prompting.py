from __future__ import annotations

from collections.abc import Mapping, Sequence

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
    prior = prior_text(differences, bugs, int(PROMPT_BUDGET * PRIOR_SHARE))

    if totals is None:
        # Everything was read, so send everything whenever the whole prompt fits.
        # Going through `reserve` first would charge the outline as if nothing
        # were sent - the long list with a row for every part - and then drop
        # real parts that `fits_whole` had just promised would fit. With every
        # part included the outline is only a short list of files.
        #
        # THE PARTS COME FIRST: the lines of what was found get only the room
        # the parts leave. On 2026-10-24 the findings of a stuffed run (F5) cut
        # B from 82 parts to 65; the code is the evidence, a finding line is a
        # hint about it.
        bare = build_prompt(
            chunks,
            chunks,
            question=question,
            instructions=instructions,
            summaries=summaries,
            last_answer=last_answer,
        )
        room = PROMPT_BUDGET - estimate_tokens(bare) - PRIOR_LABEL_TOKENS
        limit = min(int(PROMPT_BUDGET * PRIOR_SHARE), room)
        fitted = prior_text(differences, bugs, limit) if limit > 0 else ""
        prompt = build_prompt(
            chunks,
            chunks,
            question=question,
            instructions=instructions,
            prior=fitted,
            summaries=summaries,
            last_answer=last_answer,
        )
        if estimate_tokens(prompt) <= PROMPT_BUDGET:
            return prompt, chunks

    # On the search path the parts behind the findings go FIRST on their side,
    # so the cut for room drops a search hit before the code a finding is
    # about (R20). The selector keeps the order it is given. The IDS stay on
    # `chunks` with any missing deciding part at the end (`respond` saves that
    # same list), or the page would resolve every citation against a list
    # numbered differently.
    order = chunks
    if evidence:
        order = _first(evidence, chunks)
        held = {(chunk.artifact_id, chunk.chunk_index) for chunk in chunks}
        chunks = (
            *chunks,
            *(c for c in order if (c.artifact_id, c.chunk_index) not in held),
        )

    overhead = reserve(
        chunks,
        question=question,
        instructions=instructions,
        prior=prior,
        summaries=summaries,
        last_answer=last_answer,
    )
    room = PROMPT_BUDGET - overhead
    selected = select(order, budget=room) if room > 0 else ()
    prompt = build_prompt(
        chunks,
        selected,
        question=question,
        instructions=instructions,
        prior=prior,
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
