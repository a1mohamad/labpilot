from collections.abc import Sequence

from labpilot.agent import DIFFERS, MISSING, SILENT, Bug, Difference
from labpilot.tokens import estimate_tokens

# A finding line is cut at this length, so twenty of them stay near 2,000
# tokens whatever the model wrote.
LINE_CHARS = 300

DIFFERENCES_NOTE = (
    "A's facts were checked against B, and B was read beside A. [B differs] "
    "means A states it and B does it otherwise; [B leaves out] means A states a "
    "rule and B never does it; [A silent] means B does it and A never says it. "
    "[unclear] means the reviewers did not agree it is real. Check each line "
    "against the parts before you rely on it."
)
BUGS_NOTE = (
    "The file was also read alone, to find its defects: in the code, the "
    "logic, the method, the numbers and the idea. A second reviewer judged each "
    "one: [real] it is wrong, [unclear] it could not be decided, [unchecked] "
    "no reviewer answered. Check each against the parts before you rely on it."
)

_TAGS = {DIFFERS: "B differs", MISSING: "B leaves out", SILENT: "A silent"}

# The most telling lines come first, so a line cut for room is the least
# telling one: what B does otherwise or leaves out, then a real bug that
# changes results, then the rest.
_DIFFERENCE_RANK = {DIFFERS: 0, MISSING: 0, SILENT: 2}
_BUG_RANK = {("real", "high"): 1, ("real", "low"): 2}
_LAST = 3


def _cut(line: str) -> str:
    return line if len(line) <= LINE_CHARS else line[: LINE_CHARS - 1] + "…"


def difference_line(found: Difference) -> str:
    tag = _TAGS[found.kind] + (", unclear" if found.unclear else "")
    line = f"[{tag}] {found.text}"
    if found.fact:
        line += f' A states: "{found.fact}".'
    if found.quote:
        line += f' B ({found.source}): "{found.quote}".'
    return _cut(line)


def bug_line(bug: Bug) -> str:
    return _cut(
        f'[{bug.verdict} - {bug.kind}] {bug.text} ({bug.source}): "{bug.quote}".'
    )


def _rank_difference(found: Difference) -> int:
    return _LAST if found.unclear else _DIFFERENCE_RANK[found.kind]


def prior_text(
    differences: Sequence[Difference], bugs: Sequence[Bug], limit: int
) -> str:
    """The lines of what was already found, the most telling first, within
    `limit` tokens. What does not fit is counted in one line, never lost
    silently."""
    entries = [
        (_rank_difference(d), "difference", difference_line(d)) for d in differences
    ]
    entries += [
        (_BUG_RANK.get((b.verdict, b.severity), _LAST), "bug", bug_line(b))
        for b in bugs
    ]

    spent = 0
    if differences:
        spent += estimate_tokens(DIFFERENCES_NOTE)
    if bugs:
        spent += estimate_tokens(BUGS_NOTE)
    kept: list[tuple[int, str, str]] = []
    left_out = 0
    for entry in sorted(entries, key=lambda entry: entry[0]):
        cost = estimate_tokens(entry[2]) + 1
        if spent + cost > limit:
            left_out += 1
            continue
        kept.append(entry)
        spent += cost

    blocks = []
    for kind, note in (("difference", DIFFERENCES_NOTE), ("bug", BUGS_NOTE)):
        lines = [line for _, of, line in kept if of == kind]
        if lines:
            blocks.append("\n".join([note, *lines]))
    if left_out:
        blocks.append(
            f"({left_out} more lines of findings were left out for room, the "
            "least telling first.)"
        )
    return "\n\n".join(blocks)
