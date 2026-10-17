from collections.abc import Sequence

from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens

SUMMARY_BUDGET = 12_000
SUMMARY_MAX_TOKENS = 4_000

SUMMARY = Instructions(
    name="summary",
    header="""\
You are reading one piece of work: a paper, a notebook, or code.
Say what it is and what it does, in plain prose.

It is given as parts, one after the other. Each part starts with a line that
names where it comes from. The line before the first part says how many parts
there are and how many were sent to you.
If some were not sent, describe only what you read, and say that the rest
was not read. Do not guess what the missing parts contain.

Write no headings and no lists. Give no advice and no opinion.""",
    closing=(
        "Write the summary now. At most 150 words, only what the parts above show."
    ),
)


def build_summary_prompt(parts: Sequence[str]) -> str:
    if not parts:
        raise ValueError("a summary needs at least one part")

    sent: list[str] = []
    used = 0
    for part in parts:
        cost = estimate_tokens(part)
        if used + cost > SUMMARY_BUDGET:
            break
        sent.append(part)
        used += cost

    if len(sent) == len(parts):
        status = f"All {len(parts)} parts are sent to you below."
    else:
        status = (
            f"Only the first {len(sent)} of {len(parts)} parts are sent to you "
            "below. The rest were not sent."
        )

    return "\n\n".join([SUMMARY.header, status, *sent, SUMMARY.closing])
