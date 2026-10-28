from collections.abc import Sequence

from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number, which is
# logged beside every list of code findings.
DIFFERENCES_VERSION = 1

# B is read in groups of about this size, each beside ALL of A, one call for
# each group, all at the same time. Measured 2026-10-25 on the sample pair
# (section 26): about 34 items for B, most of them real differences, among them
# the stop-word mask, the pooled projections and the cosine feature, which no
# claim of A reaches.
DIFFERENCES_GROUP_TOKENS = 2_000

# A is put WHOLE beside every group, so it must be small. Above this the step
# does not run (a big A is slice 12).
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
Two files describe the same work. A is the reference: it says how the work was
done. B is another implementation of it. Their results differ, and we want to
know why. You see ALL of A and SOME parts of B.

List what these parts of B do that can change what B computes or the numbers it
reports, AND that A does differently or never says. One thing for each item, in
your own words, with its names and values. Look for:
- a value, a setting or a step that differs from A;
- something B does that A never mentions: masking, dropping, filtering or
  capping data, an extra feature, a different loss, metric, threshold or split;
- something B builds or defines and never uses, or turns off with a flag (name
  the flag), when A says the work uses it;
- a comment in B that says it does something other than A;
- an input that makes B behave wrongly (an empty input, an input where
  everything is masked), when these parts show it;
- B's own reported numbers: read every number, and when two numbers describe
  the same thing on two sets (train and validation), give both.
Leave out what B does the same way as A, and leave out logging, file paths,
printing and code style.

For each item give: the number of the part of B it comes from; the quote, the
exact words of that part of B (one line of code is best), copied letter for
letter, at most 200 characters; and what A says about it, in A's words, or
"A does not say" when A is silent.""",
    closing="List every such item in these parts of B, or none if there is none.",
)


def build_differences_prompt(a_parts: Sequence[str], b_parts: Sequence[str]) -> str:
    if not a_parts or not b_parts:
        raise ValueError("the step needs parts of A and parts of B")

    numbered = [f"[part {number}]\n{part}" for number, part in enumerate(b_parts)]
    return "\n\n".join(
        [
            DIFFERENCES.header,
            "FILE A, WHOLE",
            "\n\n".join(a_parts),
            "PARTS OF FILE B",
            *numbered,
            DIFFERENCES.closing,
        ]
    )
