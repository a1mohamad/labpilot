from __future__ import annotations

from collections.abc import Mapping, Sequence

from labpilot.agent import A_SILENT, CodeFinding, Finding
from labpilot.api.errors import (
    ArtifactsTooLargeToCompare,
)
from labpilot.ingest import (
    Chunk,
)
from labpilot.prompts import (
    CHECKS_NOTE,
    PROMPT_BUDGET,
    build_chat_prompt,
    build_prompt,
    instructions_for,
    render_checks,
    reserve,
)
from labpilot.retrieval import select
from labpilot.tokens import estimate_tokens

# A line of the checks is cut at this length, so twenty of them stay near 2,000
# tokens whatever the model wrote.
CHECK_LINE_CHARS = 300
_SHOWN_FIRST = {"mismatch": 0, "absent": 1, "unchecked": 2, "match": 3}


def _check_line(finding: Finding) -> str:
    claim = finding.claim
    tag = f"{finding.verdict} - {finding.kind}" if finding.kind else finding.verdict
    line = f'[{tag}] A says "{claim.text}" ({claim.source}).'
    if finding.quote:
        line += f' B ({finding.source}): "{finding.quote}".'
    if finding.note:
        line += f" {finding.note}"
    if len(line) > CHECK_LINE_CHARS:
        line = line[: CHECK_LINE_CHARS - 1] + "…"
    return line


def checks_text(findings: Sequence[Finding]) -> str:
    ordered = sorted(findings, key=lambda found: _SHOWN_FIRST[found.verdict])
    return render_checks([_check_line(found) for found in ordered])


CODE_NOTE = (
    "B was also read part by part beside the whole of A, to find what B does "
    "that A does otherwise or never says. [B differs] means A states something "
    "else; [A silent] means A does not mention it. Each line is one reading of "
    "the code: check it against the parts before you rely on it."
)


def _code_line(found: CodeFinding) -> str:
    tag = "A silent" if found.a_says == A_SILENT else "B differs"
    line = f'[{tag}] {found.text} B ({found.source}): "{found.quote}".'
    if found.a_says != A_SILENT:
        line += f' A says: "{found.a_says}".'
    if len(line) > CHECK_LINE_CHARS:
        line = line[: CHECK_LINE_CHARS - 1] + "…"
    return line


def code_findings_text(found: Sequence[CodeFinding]) -> str:
    if not found:
        return ""
    return "\n".join([CODE_NOTE, *(_code_line(item) for item in found)])


# The lines of what was already found get at most this share of the prompt's
# budget. On 2026-10-25 48 check lines and 33 code lines, with the instruction
# and the outline, came to more than a 12,000-token budget, and the answer was
# refused with ArtifactsTooLargeToCompare. The lines that tell the most are kept.
PRIOR_SHARE = 0.25
# What the block around the finding lines adds to the prompt (its title and
# the blank lines), kept free when the lines are fitted into the room left.
PRIOR_LABEL_TOKENS = 200
# A match line in short form: the claim alone. The writer needs the mismatches
# in full; a match only says what not to report.
_MATCH_CHARS = 140
_RANK = {"mismatch": 0, "differs": 1, "absent": 2, "unchecked": 3, "silent": 4}


def prior_text(
    findings: Sequence[Finding],
    code_findings: Sequence[CodeFinding],
    limit: int,
) -> str:
    """The checks and the code findings, the most telling lines first, within
    `limit` tokens. What does not fit is counted in one line, never lost
    silently."""
    entries: list[tuple[int, str, str]] = []
    for found in findings:
        if found.verdict == "match":
            line = f'[match] A says "{found.claim.text}"'[:_MATCH_CHARS]
            entries.append((5, "check", line))
        else:
            entries.append((_RANK[found.verdict], "check", _check_line(found)))
    for item in code_findings:
        rank = _RANK["silent"] if item.a_says == A_SILENT else _RANK["differs"]
        entries.append((rank, "code", _code_line(item)))

    notes = estimate_tokens(CHECKS_NOTE) + estimate_tokens(CODE_NOTE)
    kept: list[tuple[int, str, str]] = []
    spent = notes
    left_out = 0
    for entry in sorted(entries, key=lambda entry: entry[0]):
        cost = estimate_tokens(entry[2]) + 1
        if spent + cost > limit:
            left_out += 1
            continue
        kept.append(entry)
        spent += cost

    blocks = []
    checks = [line for _, kind, line in kept if kind == "check"]
    codes = [line for _, kind, line in kept if kind == "code"]
    if checks:
        blocks.append(render_checks(checks))
    if codes:
        blocks.append("\n".join([CODE_NOTE, *codes]))
    if left_out:
        blocks.append(
            f"({left_out} more lines of findings were left out for room, the "
            "least telling first.)"
        )
    return "\n\n".join(blocks)


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
    findings: Sequence[Finding] = (),
    code_findings: Sequence[CodeFinding] = (),
    evidence: Sequence[Chunk] = (),
) -> tuple[str, tuple[Chunk, ...]]:
    if files == 0:
        return build_chat_prompt(question, last_answer), ()

    instructions = instructions_for(files)
    # The checks ride in the block that already carries what an earlier pass
    # found, so `build_prompt` and `reserve` both count them.
    prior = prior_text(findings, code_findings, int(PROMPT_BUDGET * PRIOR_SHARE))

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
        fitted = prior_text(findings, code_findings, limit) if limit > 0 else ""
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
