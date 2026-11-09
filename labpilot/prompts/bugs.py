from collections.abc import Sequence
from dataclasses import dataclass

from labpilot.prompts._groups import numbered_parts
from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number, which is
# logged beside every list of bugs. Measured on 2026-10-31 and 2026-11-01 on
# three cases (section 29).
BUGS_VERSION = 3

# The trace question reads one group of about this size at a time, all groups
# at the same time.
TRACE_GROUP_TOKENS = 2_000
# The method and the concept questions and the checklist audit read the WHOLE
# file, in groups of about this size: their evidence is spread (the numbers at
# the top, the evaluation at the bottom). 19,000 tokens were read in one call
# when it was measured. It is a target: a group boundary moves to the edge of a
# file that fits in one group (D94).
WHOLE_GROUP_TOKENS = 24_000
# How much of one artifact a question may scan, in whole files (D94): a file
# that does not fit is skipped, and the log says how many were not read. This
# number and how the files are chosen are first guesses (slice 12, 29.8).
BUGS_SCAN_TOKENS = 40_000
# The skeptic reads the whole scanned file when it is at most this size, and
# only the suspects' own parts when it is bigger.
SKEPTIC_TOKENS = 30_000
# At most this many suspects are judged in one call.
SKEPTIC_BATCH = 25
# Each batch is judged this many times, at the same time (see DROP_VERDICTS).
SKEPTIC_VOTES = 2
# Short answers, but a tier that thinks spends tokens first: backstops only.
BUGS_MAX_TOKENS = 12_000
SKEPTIC_MAX_TOKENS = 8_000

_FOR_EACH = """\
For each defect give: the kind; the number of the part it is in; the quote, the
exact words of that part (one line of code is best), copied letter for letter,
at most 200 characters; what is wrong and what it causes, in one or two
sentences; and the severity: "high" if it changes results, "low" otherwise."""

_CLOSING = "List every real defect in these parts, or none if there is none."

TRACE = Instructions(
    name="bugs-trace",
    header=f"""\
You are reviewing parts of one piece of work: code, a notebook or a script.
Find real defects of two kinds:
- "code": an input or a state that makes it crash or compute a wrong value;
- "logic": it does not do what its own names, comments, documentation or
  purpose say, or the algorithm itself is wrong for that purpose.

Work through every function and block in these parts, one by one:
1. What is it meant to compute? Use its name, its comments, its documentation
   and the summary of the whole work.
2. If it implements a known algorithm, formula or standard, compare it with
   the standard form, term by term: every constant, sign, exponent, index,
   mask, rounding and the order of the steps.
3. Run it in your head on its FIRST call and on edge inputs: zero, empty, one
   element, the first step, the last index, all values equal or all masked.
   Does it still compute the right thing, or crash, or divide by zero?
4. Check that every setting really takes effect, every check accepts exactly
   what it should, and two functions that must agree really agree.
5. Check the ORDER and the SIGNS: a counter, a step number or a state must be
   updated before the code that needs the new value uses it, and every term of
   a formula has the right sign (+ or -) and the right variable.

List every suspect you find, even when you are not sure: a second reviewer
checks each one. Report only what you can point at in the text. Do not report
style, naming, missing comments, missing tests, or something that is only
unusual.

{_FOR_EACH}""",
    closing=_CLOSING,
)

METHOD = Instructions(
    name="bugs-method",
    header="""\
You are reviewing one piece of work: code, a notebook or a script, with any
numbers it reports. Look ONLY at how its experiments, tests or measurements are
run, and at its numbers:
- "method": data used twice; a choice tuned on the same data that is then
  reported; no held-out data; one run or one seed where the result needs
  several; a metric that does not measure what is claimed; a control missing;
- "numbers": read EVERY block of numbers in the work (comments, docstrings,
  outputs, logs). Compare numbers that describe the same thing (train against
  validation, before against after, reported against computed) and say what a
  large gap means.
List every suspect, even when you are not sure: a second reviewer checks each
one. If the work runs no experiment and reports no numbers, list none.

For each defect give: the kind; the number of the part it is in; the quote, the
exact words of that part, copied letter for letter, at most 200 characters; what
is wrong and what it causes, in one or two sentences; and the severity: "high"
if it changes results, "low" otherwise.""",
    closing=_CLOSING,
)

CONCEPT = Instructions(
    name="bugs-concept",
    header="""\
You are reviewing one piece of work: code, a notebook or a script, as an expert
in its field would. Code can run without any error and still be built on a
wrong idea. Look ONLY for that kind of defect, the kind "concept":
- a choice that defeats the purpose of the work: it removes or hides
  information the task needs, or changes the meaning of the data or the input;
- a choice an expert in this field knows is unsafe or wrong: a key, a limit or
  a size that is too weak; something that must be used once and can be used
  again; a check or a comparison that leaks information or can be bypassed; a
  known pitfall of the method or the algorithm;
- a default value outside what the standards or the common practice of the
  field allow;
- an assumption the work relies on that is false for the data it handles.
For each one say why an expert would call it a mistake and what it costs.
List every suspect, even when you are not sure: a second reviewer checks each
one. Do not report crashes, typos, style or missing tests: other reviewers look
at those. If you find none, list none.

For each defect give: the kind ("concept"); the number of the part it is in;
the quote, the exact words of that part (one line of code is best), copied
letter for letter, at most 200 characters; what is wrong and what it causes, in
one or two sentences; and the severity: "high" if it changes results or
safety, "low" otherwise.""",
    closing=_CLOSING,
)

SKEPTIC = Instructions(
    name="bugs-skeptic",
    header="""\
You check suspected defects of one piece of work. Each suspect was written by a
reviewer who may be wrong. For each suspect, read the code it points at and
decide:
- "real": the code really does this, and it is wrong for what the work is meant
  to do;
- "intended": the code does this on purpose, or it is a documented and
  acceptable choice, or it does not change any result;
- "false": the code does not do what the suspect says (a misreading);
- "unclear": the text you see is not enough to decide;
- "repeat": the same defect as an EARLIER suspect in this list (the same cause,
  even if it is quoted from another line): give that suspect's number as
  same_as.
A claim that the code does not compile or has a syntax error is "false" when
the code you see is valid (for example two "else" at different indents are a
nested if). A defect of METHOD (how an experiment, test or measurement is run: data used
twice, tuning on the data that is reported, one run or one seed) or of NUMBERS
(numbers that disagree, a large gap the work reports without comment) is a real
defect even when the code runs without error. "It is common practice" and "it
is an outcome, not code" are not reasons for "intended". A defect of CONCEPT
(a choice an expert in the field knows is wrong or unsafe: information the task
needs is thrown away, a key or a limit is too weak, a check leaks or can be
bypassed) is real even when the code does exactly what it says.
Be strict: "real" only when you can say what goes wrong. Give a one-sentence
reason. Answer for every suspect, by its number.""",
    closing="",
)


@dataclass(frozen=True, slots=True)
class Hunt:
    """One question that looks for suspects, and how it reads the file.

    `small` questions are many short calls (one for each small group), so they
    go to a cheap chain (D93). The others read the whole file in big groups,
    whose edges follow the files (`by_file`).
    """

    instructions: Instructions
    group_tokens: int
    with_summary: bool
    small: bool = False
    by_file: bool = True


HUNTS = (
    Hunt(TRACE, TRACE_GROUP_TOKENS, with_summary=True, small=True, by_file=False),
    Hunt(METHOD, WHOLE_GROUP_TOKENS, with_summary=False),
    Hunt(CONCEPT, WHOLE_GROUP_TOKENS, with_summary=True),
)


def build_hunt_prompt(
    instructions: Instructions, parts: Sequence[str], summary: str = ""
) -> str:
    if not parts:
        raise ValueError("a hunt needs at least one part")

    context = ["WHAT THE WHOLE WORK IS (a summary)", summary] if summary else []
    numbered = numbered_parts(parts)
    return "\n\n".join(
        [instructions.header, *context, "THE PARTS", *numbered, instructions.closing]
    )


def build_skeptic_prompt(parts: Sequence[str], suspects: Sequence[str]) -> str:
    if not suspects:
        raise ValueError("the skeptic needs at least one suspect")

    listed = "\n".join(f"{number}. {line}" for number, line in enumerate(suspects))
    return "\n\n".join([SKEPTIC.header, "THE CODE", *parts, "SUSPECTS", listed])
