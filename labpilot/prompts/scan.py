from collections.abc import Sequence

from labpilot.prompts._groups import numbered_parts
from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number.
SCAN_VERSION = 1

# B is read in groups of about this size. A's own text goes beside each group
# when A is at most SCAN_A_TEXT_TOKENS; a bigger A is shown as its list of facts.
SCAN_GROUP_TOKENS = 2_000
SCAN_A_TEXT_TOKENS = 20_000
SCAN_MAX_TOKENS = 8_000

SCAN = Instructions(
    name="scan",
    header="""\
A is a reference: a paper, a standard or an original program. B is an
implementation of it. Below is what A states, and then some parts of B.

List what B does that A NEVER says, when it can change the result: the numbers
B computes, the inputs it accepts, rejects or rewrites, or the values it
returns. For example: an extra step, an option that switches to another variant
of the method, a default used when the input gives none, what B does with an
unusual or invalid input, a constant that A does not give.
Do NOT list: anything A states (even in other words, and even if B does it
differently: another reviewer checks those); a faster way to compute the same
numbers; logging, printing, files, tests or style; a setting that is off.
For each item give the part number, a quote (one line of B, copied letter for
letter), what B does, and why it can change the result.""",
    closing="List none if there is none.",
)


def build_scan_prompt(reference: str, parts: Sequence[str]) -> str:
    """`reference` is A's text, or its facts as lines when A is too big."""
    if not reference.strip():
        raise ValueError("the scan needs what A states")
    if not parts:
        raise ValueError("the scan needs at least one part of B")

    numbered = numbered_parts(parts)
    return "\n\n".join(
        [
            SCAN.header,
            "WHAT A STATES",
            reference,
            "THE CODE OF B",
            *numbered,
            SCAN.closing,
        ]
    )
