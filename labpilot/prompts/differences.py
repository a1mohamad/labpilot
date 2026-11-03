from collections.abc import Sequence

from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number, which is
# logged beside every list of code findings.
DIFFERENCES_VERSION = 2

# B is read in groups of about this size, one call for each group, all at the
# same time.
DIFFERENCES_GROUP_TOKENS = 2_000

# How many parts of A are shown beside each group of B: the nearest part of A
# for each part of B, the first ones of the group, no repeats. Measured on
# 2026-10-31 (section 29): with them the scan wrote 0-2 items a run that A
# already states, against 3-7 with the list of claims alone.
NEAR_A_PARTS = 3

# The largest A that is read WHOLE on the search path (whole_side). The scan
# no longer puts A beside B: it reads the claims and the nearest parts.
A_WHOLE_TOKENS = 10_000

# How much of B one question may scan. Above it, the first parts up to it are
# scanned and the log says how many were not (ranking them is slice 12).
SCAN_TOKENS = 40_000

# A list of short items, but a tier that thinks spends tokens first, so this is
# only a backstop.
DIFFERENCES_MAX_TOKENS = 8_000

DIFFERENCES = Instructions(
    name="differences",
    header="""\
A is a reference: it says how some work is done. B implements that work. Below
is the list of FACTS that A states, then the parts of A that are closest to
these parts of B, and then some PARTS of B.

List what these parts of B do that can change what B computes, accepts, returns
or reports, in two kinds:
- "silent": B does it and NO fact in the list states it. Think of: a step, a
  filter, a default value, a limit or a cap, an extra option or feature, a
  special case, a way of handling unusual input.
- "differs": a fact in the list states it, and B does it differently. Give the
  number of that fact.
One thing for each item, in your own words, with its names and values. Leave
out what B does the same way as a fact, and leave out logging, printing, file
paths, error messages, tests and code style.

For each item give: the kind; the fact number for "differs" (-1 for
"silent"); the number of the part of B it comes from; the quote, the exact
words of that part (one line of code is best), copied letter for letter, at
most 200 characters; and a topic of one to three words.""",
    closing="List every such item in these parts of B, or none if there is none.",
)


def build_differences_prompt(
    facts: Sequence[str], a_parts: Sequence[str], b_parts: Sequence[str]
) -> str:
    if not b_parts:
        raise ValueError("the step needs parts of B")

    listed = "\n".join(f"{number}. {fact}" for number, fact in enumerate(facts))
    numbered = [f"[part {number}]\n{part}" for number, part in enumerate(b_parts)]
    return "\n\n".join(
        [
            DIFFERENCES.header,
            "FACTS THAT A STATES",
            listed or "(none)",
            "THE PARTS OF A CLOSEST TO THESE PARTS OF B",
            "\n\n".join(a_parts) or "(none)",
            "PARTS OF B",
            *numbered,
            DIFFERENCES.closing,
        ]
    )
