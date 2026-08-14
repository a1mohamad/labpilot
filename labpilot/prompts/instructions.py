from __future__ import annotations

import re
from dataclasses import dataclass

_PREAMBLE = """\
You compare two pieces of work and explain why their results differ.

A is the reference. It states what should happen.
B is the subject. It is what we are examining.

MODE
If A only describes, and B is something that runs, this is ONE-WAY.
Check what A states against what B does.
If both A and B are things that run, this is TWO-WAY.
Go topic by topic and record what each side does.
In TWO-WAY mode never say that one side is wrong. Say only that they differ.
Decide the mode yourself and say which one you chose.

WHAT YOU RECEIVE
Each side is given as a list of all its parts, in order.
Each part has a short id such as A-3 or B-17.
Parts marked "text included" have their text below the list.
Parts marked "text NOT included" were not sent to you. You have not read them."""

_RULES = """\
RULES

1. CITE EVERYTHING
   Every statement you make about A or B must give:
     - the part id, exactly as written, for example B-17
     - a short quote, copied exactly, of one whole line from that part
   Write every citation exactly like this:
       [B-17 "count = count + 1"]
   The part id, a space, then the quote in double quotes. Nothing else.
   Never write a line number. Line numbers are added for you afterwards.
   If a statement needs two parts, give two ids and two quotes.
   If you report that something is missing, cite the side that mentions it
   and name the part where you expected to find it.
   A statement with no citation will be removed.

2. SAY HOW YOU KNOW
   Seen in both sides
       -> "A states ... , B does ..."
   Seen in one side, and the matching part of the other side was not sent
       -> "not found in the text I was given"
   Known only from general knowledge, not from either side
       -> "this is unusual"   (never "this is wrong")

3. NONE IS A CORRECT ANSWER
   If a section has nothing to report, write NONE.
   Do not invent content to fill a section.

4. DO NOT COMPARE TWO VALUES until you have written how each one was made.

5. WRITE EVERY SECTION, IN ORDER. Do not skip one. Do not reorder them."""

_LABELS = """\
HOW TO LABEL EVERY DIFFERENCE

KIND
  contradiction   A states X, B does the opposite
  missing-in-B    A states X, B never does it
  missing-in-A    B does something A never mentions
  unclear-in-A    A does not say enough, so B had to choose
  defect          B is wrong on its own, ignoring A
  scope           B covers only part of A, or goes beyond A
  same-idea       the same behaviour written a different way.
                  This is NOT a difference. Record it and drop it.

BOX - where in the work it comes from
  input         what went in
  procedure     what was done to it
  measurement   how the result became a value
  environment   what machinery ran it
  reporting     which value was chosen to show

IMPACT
  direction   raises / lowers / unknown
  size        large / small / unknown
  confidence  high / medium / low"""

_CAUSES = """\
COMMON CAUSES - examples only, never a complete list

input        a different source, or a different version of it; a different
             subset or filter; a different order; different units or scaling;
             different handling of missing or invalid entries; parts that
             must stay separate got mixed together
procedure    a different method for the same goal; a step present in one side
             and absent in the other; steps in a different order; different
             settings; a different stopping point; a step that is written but
             never called; a value that is set and then replaced somewhere
             else; different handling of edge cases; different handling of
             randomness
measurement  a different quantity is measured; the same name means a
             different formula; measured at a different point, or over a
             different range; added up a different way
environment  a version change moved a default; different number precision;
             different machinery changing the order of operations; randomness
             that nobody controlled
reporting    a setting was tuned on the same data the value is reported on;
             the best of many runs was shown; one run with no spread; only
             part of the results was shown; the value came from an older
             version of the work"""

_FULL_SECTIONS = """\
§0  TASK
    One sentence: what was asked.
    Say whether this is ONE-WAY or TWO-WAY, and why.

§1  SIDE A
    What it is, and what it says it achieves. One paragraph.
    Name the parts of A whose text was not sent to you.

§2  SIDE B
    What it is, and what it actually does, in order. One paragraph.
    Name the parts of B whose text was not sent to you.

§3  CORRESPONDENCE
    Do A and B describe the same work?   FULL / PARTIAL / NONE
    PARTIAL: say what overlaps and what does not.
    NONE: give your reason and STOP. Write no section below this one.

§4  PROBLEMS IN B ALONE
    Problems in B that need no reference at all.
    Each one: what, where, why, and how you know.
    May be NONE.

§5  REPORTED RESULTS
    One row for each value either side reports:
      value | what produced it | how it was measured | how it was chosen | citation
    May be NONE. Many comparisons report nothing.

§6  CAN THEY BE COMPARED?
    For each pair of values from §5: YES / NO / CANNOT TELL, and why.
    If NO or CANNOT TELL, no difference between those two values may be
    calculated anywhere below.

§7  DIFFERENCES
    One row each, numbered D1, D2, D3 ...
      id | kind | box | how you know | A citation | B citation |
      direction | size | confidence | one sentence
    ONE-WAY: first every statement A makes, then every decision B makes that
    A never mentions.
    TWO-WAY: one pass, topic by topic.
    Finish this list completely before you write anything below it.

§8  RANKING
    The same D numbers, ordered by how much each one could change the result.
    Say why the top ones are on top.

§9  DOES IT ADD UP?
    What §8 would predict, against what §5 actually shows.
    CLOSES / DOES NOT CLOSE / NOT APPLICABLE.
    If it does not close, give every honest reading. Do not pick one.
    Do not change anything above to make it close.

§10 EXPLANATION
    The causal story. Use only D numbers from §7. Add no new claims here.

§11 WHAT COULD NOT BE DETERMINED
    What was missing, which parts were not sent to you, and what would
    settle each open question.

§12 CORRECTIONS
    Concrete changes to B. Each one: the change, where, the expected effect,
    and your confidence.

§13 NEXT STEP
    One experiment. What it would settle, and what each possible result
    would mean."""

_CORE_SECTIONS = """\
§0  TASK
    One sentence: what was asked.
    Say whether this is ONE-WAY or TWO-WAY.

§1  WHAT EACH SIDE IS
    One paragraph for A, one for B.
    Name the parts whose text was not sent to you.

§2  REPORTED VALUES
    One row per value either side reports:
      value | what produced it | how it was measured | how it was chosen | citation
    Then, for each pair: can they be compared?  YES / NO / CANNOT TELL, and why.
    If NO or CANNOT TELL, no difference between them may be calculated below.
    May be NONE.

§3  DIFFERENCES
    One row each, numbered D1, D2, D3 ...
      id | kind | box | how you know | A citation | B citation |
      direction | size | confidence | one sentence
    Biggest effect first.
    Finish this list completely before you write anything below it.

§4  DOES IT ADD UP?
    What §3 would predict, against what §2 actually shows.
    CLOSES / DOES NOT CLOSE / NOT APPLICABLE.
    If it does not close, give every honest reading. Do not pick one.

§5  EXPLANATION
    The causal story. Use only D numbers from §3. Add no new claims."""


@dataclass(frozen=True, slots=True)
class Instructions:
    name: str
    header: str
    closing: str


def _numbers(text: str) -> list[int]:
    return sorted({int(found) for found in re.findall(r"§(\d+)", text)})


def _instructions(name: str, sections: str) -> Instructions:
    listed = ", ".join(f"§{number}" for number in _numbers(sections))

    header = "\n\n".join((_PREAMBLE, _RULES, _LABELS, _CAUSES, f"OUTPUT\n\n{sections}"))
    closing = (
        f"Now write the report. Write these sections, in this order:\n{listed}\n\n"
        "Cite with a part id and an exact quote. Never write a line number.\n"
        "Write NONE for any section with nothing to report."
    )
    return Instructions(name, header, closing)


FULL = _instructions("full", _FULL_SECTIONS)
CORE = _instructions("core", _CORE_SECTIONS)
