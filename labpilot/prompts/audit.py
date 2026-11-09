from collections.abc import Sequence

from labpilot.prompts._groups import numbered_parts
from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number.
AUDIT_VERSION = 1

# Facts asked in one call, the most of B one call reads, and how many
# independent runs (votes) are made (section 29.9, D97).
AUDIT_BATCH = 30
AUDIT_GROUP_TOKENS = 24_000
AUDIT_VOTES = 2
AUDIT_MAX_TOKENS = 12_000
# How much of B the audit and the scan read, in whole files (D94). Above it, a
# file that does not fit is skipped and the log says so (a big B is slice 12).
DIFFERENCES_READ_TOKENS = 40_000

AUDIT = Instructions(
    name="audit",
    header="""\
A is a reference: a paper, a standard or an original program. B is an
implementation of it. Below is a numbered list of FACTS that A states, and then
the code of B.

Answer for EVERY fact, by its number, with one verdict:
- "same": B does what the fact says.
- "differs": B does it, but differently: another value, formula, condition,
  order, range or default.
- "missing": the fact is a rule B must follow (a check, a limit, a step, a
  value to reject, an error to raise) and B never does it anywhere.
- "n/a": the fact only describes or defines something, is about a part of the
  work B does not implement, or cannot be seen in code.
Read all of B before you say "missing": the rule may be done in another part.
A rule can apply in more than one place (for example where B reads a value and
where B writes it): say "differs" if any place breaks it.
Judge what the code does, not what its comments say.
For "differs" and "missing" also give the part number, a quote (one line of B,
copied letter for letter; for "missing", the line where B should do it) and one
sentence: what B does, and what it changes.""",
    closing="Answer every fact by its number.",
)


def build_audit_prompt(
    facts: Sequence[str], numbers: Sequence[int], parts: Sequence[str]
) -> str:
    if not numbers:
        raise ValueError("the audit needs at least one fact")
    if not parts:
        raise ValueError("the audit needs at least one part of B")

    listed = "\n".join(f"{n}. {facts[n]}" for n in numbers)
    numbered = numbered_parts(parts)
    return "\n\n".join(
        [
            AUDIT.header,
            "FACTS THAT A STATES",
            listed,
            "THE CODE OF B",
            *numbered,
            AUDIT.closing,
        ]
    )
