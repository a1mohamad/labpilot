from collections.abc import Sequence
from dataclasses import replace

from labpilot.agent.bug import (
    FALSE,
    INTENDED,
    REAL,
    REPEAT,
    SKEPTIC_VERDICTS,
    UNCHECKED,
    UNCLEAR,
    Bug,
)

SKEPTIC_TOOL_NAME = "judge_suspects"

# A suspect is thrown out only when EVERY vote says one of these. Measured on
# 2026-11-01 (section 29): one vote dropped up to 6 of 17 real defects in a bad
# run; two votes that must agree kept 16 of 17 in both pairs of runs.
DROP_VERDICTS = (FALSE, INTENDED, REPEAT)
# A CONCEPT suspect breaks a rule of the field, and the skeptic often calls that
# "intended" because the code does it on purpose (a 10-byte secret, MD5, no
# replay check). Measured on 2026-11-01: the rule above dropped 4 of the 5
# concept defects the checklist found. So a concept suspect is thrown out only
# when every vote says "false" (a misreading); "intended" makes it "unclear".
CONCEPT_DROP_VERDICTS = (FALSE, REPEAT)

# One vote about one suspect: (verdict, reason), or None when none came.
Vote = tuple[str, str] | None


def skeptic_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer"},
                        "verdict": {"type": "string", "enum": list(SKEPTIC_VERDICTS)},
                        "same_as": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["n", "verdict"],
                },
            },
        },
        "required": ["verdicts"],
    }


def _index(value: object, below: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value < below else None


def read_verdicts(arguments: dict[str, object] | None, count: int) -> list[Vote]:
    """The verdict of each of `count` suspects, by number; None where none came."""
    got: list[Vote] = [None] * count
    verdicts = arguments.get("verdicts") if isinstance(arguments, dict) else None
    if not isinstance(verdicts, list):
        return got
    for item in verdicts:
        if not isinstance(item, dict):
            continue
        number, verdict = _index(item.get("n"), count), item.get("verdict")
        if number is None or verdict not in SKEPTIC_VERDICTS:
            continue
        # A repeat must name an EARLIER suspect, or two suspects could drop
        # each other.
        if verdict == REPEAT and _index(item.get("same_as"), number) is None:
            continue
        reason = item.get("reason")
        got[number] = (verdict, reason.strip() if isinstance(reason, str) else "")
    return got


def judged_bug(bug: Bug, votes: Sequence[Vote]) -> Bug | None:
    """The suspect with its label, or None when every vote throws it out.

    One vote that says "real" makes it real. It is thrown out only when every
    vote answered and every one said false or intended (for a concept suspect:
    false), so a lost vote or a split one keeps it, labelled "unclear".
    """
    given = [vote for vote in votes if vote is not None]
    if not given:
        return replace(bug, verdict=UNCHECKED)
    for verdict, reason in given:
        if verdict == REAL:
            return replace(bug, verdict=REAL, reason=reason)
    drop = CONCEPT_DROP_VERDICTS if bug.kind == "concept" else DROP_VERDICTS
    if len(given) == len(votes) and all(v in drop for v, _ in given):
        return None
    return replace(bug, verdict=UNCLEAR, reason=given[0][1])
