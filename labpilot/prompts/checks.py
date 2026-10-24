from collections.abc import Sequence

from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number, which is
# logged beside every check.
CHECK_VERSION = 2

# One verdict and one short sentence, but a tier that thinks spends tokens first,
# so this is only a backstop.
CHECK_MAX_TOKENS = 2_000

CHECK = Instructions(
    name="check",
    header="""\
A reference says how some work was done. Below is ONE claim from the reference,
and the parts of the other file that a search found for it.

Say what the other file does about the claim:
match     a part shows the other file doing what the claim says.
mismatch  a part shows the other file doing something different. Say what kind:
          choice (it looks deliberate, and both ways are reasonable), mistake
          (it looks wrong by its own logic) or unclear.
absent    none of the parts says either way.

Read only the parts you are given. "absent" means "not found in these parts",
never "the other file does not do it".
Something that is only defined and never used or called (a helper, a value, a
setting) does not do what the claim says: look for where it is used.
For a match or a mismatch, give the number of the part that decides it, and the
quote: the exact words of that part, copied letter for letter, at most 200
characters. Then one short sentence that says why.""",
    closing="Give your verdict now.",
)

CHECKS_NOTE = (
    "Each claim of side A was checked alone against the parts of side B that a "
    "search found for it. [match], [mismatch] and [absent] come from that check. "
    "[absent] means not found in those parts, so say 'not found', never 'B does "
    "not do it'. [unchecked] means the check could not run."
)


def build_check_prompt(
    claim: str, place: str, parts: Sequence[str], facts: str = ""
) -> str:
    if not claim.strip():
        raise ValueError("a check needs a claim")
    if not parts:
        raise ValueError("a check needs at least one part")

    numbered = [f"[part {number}]\n{part}" for number, part in enumerate(parts)]
    blocks = [
        CHECK.header,
        f"THE CLAIM (from {place})\n{claim}",
        "THE PARTS OF THE OTHER FILE",
        *numbered,
    ]
    # Facts read from the WHOLE other file, which no single part can show (R8).
    if facts.strip():
        blocks.append(f"FACTS FROM THE WHOLE OTHER FILE\n{facts.strip()}")
    blocks.append(CHECK.closing)
    return "\n\n".join(blocks)


def render_checks(lines: Sequence[str]) -> str:
    return "\n".join([CHECKS_NOTE, *lines]) if lines else ""
