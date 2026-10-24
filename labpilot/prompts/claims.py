from collections.abc import Sequence

from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens

# The wording below is FIXED. Change it only together with this number, and the
# number is logged beside every list of claims, so a list can be tied to its
# wording.
CLAIMS_VERSION = 3

# The reference is read WHOLE or not at all: a fact we cut off is a question we
# never ask. A reference larger than this gets no claims (a big A is slice 12).
CLAIMS_BUDGET = 28_000

# The reference is read in GROUPS of parts of about this size, one call for each
# group, all at the same time. Measured on 2026-10-24 (section 25.2): one call
# over the whole paper (~4,300 tokens) reached about 3 of 12 known mismatch
# facts, two calls of about 2,150 tokens reached about 9, for 8 of 8 models.
# A group is never cut inside a part.
CLAIMS_GROUP_TOKENS = 2_000

# The answer of one group is a list of short claims, but a tier that thinks
# spends tokens first, so this is only a backstop.
CLAIMS_MAX_TOKENS = 6_000

CLAIMS = Instructions(
    name="claims",
    header="""\
You are reading a reference: it says how some work was done and what it found.
Another file will be checked against it, so list the facts that can be checked.

A claim is ONE fact, in the words of the reference, with its numbers and names.
"the mesh has 200 cells and the time step is 0.01 s" is two claims, not one.
If one sentence gives several values, write one claim for each value. Also write
the rules and the steps of the method as claims: how something is chosen, when
something stops, in what order things happen, what is left out.
A claim must be checkable: a value, a setting, a step, a method, or a number
the work reports. An opinion ("our method is better") is not a claim, and
neither is background.

Give each claim its kind: "method" for a value, a setting, a rule or a step of
how the work is done, and "result" for a number the work reports.

The reference comes as numbered parts: [part 0], [part 1], and so on. For each
claim, give the number of the part it comes from, and the quote: the exact words
of that part that state the claim, copied letter for letter, at most 200
characters. A claim whose quote is not in its part is thrown away.""",
    # The closing of the measured arm, word for word.
    closing="List every claim this part states, or none if it states none.",
)


def claims_fit(parts: Sequence[str]) -> bool:
    return sum(estimate_tokens(part) for part in parts) <= CLAIMS_BUDGET


def claims_groups(parts: Sequence[str]) -> list[list[int]]:
    """The parts, in order, cut into groups of about CLAIMS_GROUP_TOKENS.

    The number of groups is the total divided by the target, rounded, and every
    group gets about the same share, so 4,300 tokens become two groups of about
    2,150 and not one of 2,000 and one of 300. A part is never cut.
    """
    sizes = [estimate_tokens(part) for part in parts]
    total = sum(sizes)
    count = min(len(parts), max(1, round(total / CLAIMS_GROUP_TOKENS)))
    share = total / count if count else 0

    groups: list[list[int]] = []
    current: list[int] = []
    used = 0
    for index, size in enumerate(sizes):
        current.append(index)
        used += size
        if len(groups) < count - 1 and used >= share * (len(groups) + 1):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def build_claims_prompt(parts: Sequence[str]) -> str:
    if not parts:
        raise ValueError("claims need at least one part")
    if not claims_fit(parts):
        raise ValueError("the parts do not fit CLAIMS_BUDGET and nothing is cut")

    numbered = [f"[part {number}]\n{part}" for number, part in enumerate(parts)]
    return "\n\n".join([CLAIMS.header, "THE REFERENCE", *numbered, CLAIMS.closing])
