from collections.abc import Sequence

from labpilot.prompts._groups import numbered_parts
from labpilot.prompts.instructions import Instructions

# The checklist step of find_bugs (measured on 2026-11-01, section 29.7): two
# questions write the checklist an expert uses for this kind of work, at the
# same time, from the summary and the headers only; then CHECKLIST_AUDIT
# answers every item against the code. A concept defect a reviewer does not
# think of is found when it must answer a rule, one by one, instead of
# searching for "a wrong idea".

# Short answers, but a tier that thinks spends tokens first: backstops only.
CHECKLIST_MAX_TOKENS = 6_000
CHECKLIST_AUDIT_MAX_TOKENS = 16_000
# The checklist questions see the summary and the headers of the parts, cut to
# this many characters (6,000 when it was measured).
OUTLINE_CHARS = 6_000

STANDARDS = Instructions(
    name="bugs-standards",
    header="""\
You are an expert in the field of the work described below. Before anyone reads
its code, write the checklist an expert in this field uses to review this kind
of work. First name what it is: the task, the algorithm or method, and any
standard, specification or best practice it should follow. Then list 12 to 20
OBLIGATIONS. Each one is a short yes/no question about something the work MUST
do or must NOT do, that the code can answer:
- the MUST and MUST NOT rules of its standards or specifications;
- security and safety rules of the field (sizes and strengths of keys or
  limits, things that may be used only once, checks that must not leak or be
  bypassable);
- known pitfalls of its method or algorithm, and known better variants;
- what the input data must keep for the task to make sense.
Write each obligation so that "no" means a defect. Do not list style or
testing.""",
    closing="",
)

PITFALLS = Instructions(
    name="bugs-pitfalls",
    header="""\
You are an expert in the field of the work described below. Name the algorithm,
the method or the protocol it implements. Then list 6 to 12 OBLIGATIONS about
its KNOWN PITFALLS: weaknesses, misuses and mistakes that research or practice
in this field has found for this kind of work, and what the known fix or the
better later variant does. Write each one as a short yes/no question about what
the work must do or must not do, so that "no" means it falls into the pitfall.
Each question must be clear and must not contradict itself.""",
    closing="",
)

CHECKLIST_AUDIT = Instructions(
    name="bugs-audit",
    header="""\
You check one piece of work against a checklist an expert wrote for it. Answer
EVERY obligation, by its number, one after the other; do not skip one:
- "no": the work breaks it or leaves it undone. Give the part and the exact
  quote that shows it (when something is left undone, quote the line where it
  should happen, for example the check or the default that lacks it), and say
  what is wrong and what it costs;
- "yes": the work meets it;
- "n/a": it does not apply to this work.
Judge what the code DOES, not what its comments say.""",
    closing="",
)

# The two questions that write the checklist, at the same time.
CHECKLISTS = (STANDARDS, PITFALLS)


def build_checklist_prompt(
    instructions: Instructions, summary: str, headers: Sequence[str]
) -> str:
    outline = "\n".join(dict.fromkeys(h for h in headers if h))[:OUTLINE_CHARS]
    if not (summary or outline):
        raise ValueError("a checklist needs a summary or the headers of the parts")

    return "\n\n".join(
        [
            instructions.header,
            "WHAT THE WORK IS (a summary)",
            summary or "(no summary)",
            "ITS PARTS (headers only)",
            outline,
        ]
    )


def build_checklist_audit_prompt(
    obligations: Sequence[str], parts: Sequence[str]
) -> str:
    if not obligations:
        raise ValueError("an audit needs at least one obligation")
    if not parts:
        raise ValueError("an audit needs at least one part")

    listed = "\n".join(f"{number}. {rule}" for number, rule in enumerate(obligations))
    numbered = numbered_parts(parts)
    return "\n\n".join(
        [CHECKLIST_AUDIT.header, "THE CHECKLIST", listed, "THE PARTS", *numbered]
    )
