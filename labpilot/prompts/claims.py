from collections.abc import Sequence

from labpilot.prompts.instructions import Instructions
from labpilot.tokens import estimate_tokens

# The wording below is FIXED. Change it only together with this number, and the
# number is logged beside every list of claims, so a list can be tied to its
# wording.
CLAIMS_VERSION = 2

# The reference is read WHOLE or not at all: a fact we cut off is a question we
# never ask. Gemma (16,000 input tokens a minute) and Groq cannot take a prompt
# this large, and the length check turns them away for free, so the call goes to
# a tier that can.
CLAIMS_BUDGET = 28_000

# The answer is a list of short claims, but a tier that thinks spends tokens
# first, so this is only a backstop.
CLAIMS_MAX_TOKENS = 4_000

CLAIMS_WANTED = 15

CLAIMS = Instructions(
    name="claims",
    header="""\
You are reading a reference: it says how some work was done and what it found.
Another file will be checked against it, so list the facts that can be checked.

A claim is ONE fact, in the words of the reference, with its numbers and names.
"the mesh has 200 cells and the time step is 0.01 s" is two claims, not one.
A claim must be checkable: a value, a setting, a step, a method, or a number
the work reports. An opinion ("our method is better") is not a claim, and
neither is background.

The reference comes as numbered parts: [part 0], [part 1], and so on. For each
claim, give the number of the part it comes from, and the quote: the exact words
+of that part that state the claim, copied letter for letter, at most 200
+characters. A claim whose quote is not in its part is thrown away.

If the question names a topic, write the claims about that topic first. Do not
leave out other claims because of the question.""",
    closing=(
        f"List the claims now: at most {CLAIMS_WANTED}, the ones that matter "
        "most for the result first."
    ),
)


def claims_fit(parts: Sequence[str]) -> bool:
    return sum(estimate_tokens(part) for part in parts) <= CLAIMS_BUDGET


def build_claims_prompt(parts: Sequence[str], question: str) -> str:
    if not parts:
        raise ValueError("claims need at least one part")
    if not claims_fit(parts):
        raise ValueError("the parts do not fit CLAIMS_BUDGET and nothing is cut")

    numbered = [f"[part {number}]\n{part}" for number, part in enumerate(parts)]
    return "\n\n".join(
        [
            CLAIMS.header,
            f"THE QUESTION\n{question}",
            "THE REFERENCE",
            *numbered,
            CLAIMS.closing,
        ]
    )
