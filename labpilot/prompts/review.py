from collections.abc import Mapping, Sequence

from labpilot.prompts._groups import numbered_parts
from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number.
REVIEW_VERSION = 1

# The judge: two votes at the same time, at most this many findings a call.
JUDGE_VOTES = 2
JUDGE_BATCH = 30
JUDGE_MAX_TOKENS = 12_000
MERGE_MAX_TOKENS = 4_000

JUDGE = Instructions(
    name="judge",
    header="""\
You check findings about a program B. Each finding was written by a reviewer
who may be wrong. Read the code it points at (and what the reference A states,
when it is given) and decide:
- "real": B really does this, and it matters: it changes a result, breaks a
  rule of A, or is a defect;
- "minor": B really does this, but it changes nothing that matters: only the
  wording or the type of an error, a message, a log line, a resource that is
  not freed, or a case that a normal use never reaches;
- "false": B does not do what the finding says (a misreading, or the code is
  valid where the finding says it is broken).
Judge only whether the finding is TRUE about B; a wrong label on it is not a
reason for "false". Also say what A says about it ("relation"): "silent" (A
never says it), "differs" (A states it, and B does it differently or not at
all), "same" (B does exactly what A states) or "none" (a defect of B alone).
A finding about something B does only behind a setting that is off, zero or
never used by the run is "false" (if it says it changes results) or "minor".
A defect of method or of concept is real even when the code runs. Give one
short reason.""",
    closing="Answer every finding by its number.",
)

MERGE = Instructions(
    name="merge",
    header="""\
Below is a numbered list of findings about one program. Several of them may
make the SAME point: the same cause in the code, or the same rule of the
reference that is broken, even if they quote other lines, are written from
another side (for example "B does not check X" and "X is accepted"), or use
other words. Return the groups of findings that make the same point, each group
as a list of numbers. A finding that is alone needs no group.""",
    closing="",
)


def build_judge_prompt(
    findings: Sequence[str], first: int, parts: Sequence[str], reference: str = ""
) -> str:
    """`findings` are numbered from `first`, so several calls share one list."""
    if not findings:
        raise ValueError("the judge needs at least one finding")
    if not parts:
        raise ValueError("the judge needs the code of B")

    listed = "\n".join(f"{first + k}. {line}" for k, line in enumerate(findings))
    numbered = numbered_parts(parts)
    context = ["WHAT A STATES (the reference)", reference] if reference.strip() else []
    return "\n\n".join(
        [
            JUDGE.header,
            *context,
            "THE CODE OF B",
            *numbered,
            "FINDINGS",
            listed,
            JUDGE.closing,
        ]
    )


def build_merge_prompt(findings: Mapping[int, str]) -> str:
    """`findings`: number -> its short text with its quote."""
    if len(findings) < 2:
        raise ValueError("a merge needs at least two findings")

    listed = "\n".join(f"{n}. {line}" for n, line in findings.items())
    return "\n\n".join([MERGE.header, "FINDINGS", listed])
