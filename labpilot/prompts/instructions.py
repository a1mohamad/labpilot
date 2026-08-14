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
   One exception: in a walk, a line that reports nothing needs no quote. The
   id at the start of the line is enough. Keep those lines very short.

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
   If you answer NO or CANNOT TELL for a pair of values, those two values may
   never appear in the same sentence anywhere below.
   Do not write that one is lower than, higher than, close to, in line with,
   or consistent with the other. Do not subtract them.
   Say only that they cannot be compared, and why.

5. WRITE EVERY SECTION, IN ORDER. Do not skip one. Do not reorder them.

6. A WALK MUST BE COMPLETE.
   When a section tells you to walk a part list, write one line for every id
   in that list, in order, including the ids whose text was not sent to you.
   Writing fewer lines than there are ids is an error, even when most lines
   say "nothing". Do not stop early because the answer feels complete."""

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
    Do this in two walks, and write both before the table.
    Walk 1 — go down side A's part list, first id to last. One line for every
    id: what it states, and whether B does it, does not do it, or the place
    it would be was not sent to you.
    Walk 2 — go down side B's part list, first id to last. One line for every
    id: something it decides that A never mentions, or "nothing".
    Do not skip an id in either walk.
    Then the table, numbered D1, D2, D3 ...
      id | kind | box | how you know | A citation | B citation |
      direction | size | confidence | one sentence
    Every line of either walk that is not "nothing" becomes a row.

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
§0  WHAT EACH SIDE IS
    Say whether this is ONE-WAY or TWO-WAY, and why.
    Then one paragraph for A and one for B: what it is, and what it does.
    Name the parts whose text was not sent to you.

§1  REPORTED VALUES
    One row per value either side reports:
      value | what produced it | how it was measured | how it was chosen | citation
    Then, for each pair: can they be compared?  YES / NO / CANNOT TELL, and why.
    May be NONE.

§2  WALK SIDE A
    Go down side A's part list, from the first id to the last.
    Write one line for EVERY id:
      A-4 | says: <one thing it states should happen> | B: does it / does not
            do it / not in the text I was given
      A-5 | says nothing that can be checked
    A part may state more than one thing. Give it one line per thing.
    Do not skip an id. Do not merge two ids into one line.

§3  WALK SIDE B
    Go down side B's part list, from the first id to the last.
    Write one line for EVERY id:
      B-12 | does: <something this part decides that A never mentions>
      B-13 | nothing A does not already mention
    Do not skip an id. Do not merge two ids into one line.
    Look especially for: a limit or cap on what is kept; entries removed or
    changed before use; a step that is written but never called; a part that
    is built and never switched on; a value set in one place and replaced in
    another; an extra input added to a calculation; a name passed where it
    has no effect; an edge case A is silent about.

§4  PROBLEMS IN B ALONE
    Ignore A completely in this section.
    Ask of B: what input would make this behave wrongly, and what would
    happen then? Follow the value through, step by step.
    Each one: what, where, why, and how you know.
    May be NONE.

§5  DIFFERENCES
    Collect §2, §3 and §4 into one table, numbered D1, D2, D3 ...
      id | kind | box | how you know | A citation | B citation |
      direction | size | confidence | one sentence
    Biggest effect first.
    EVERY line of §2, §3 and §4 that is not "nothing" and not "says nothing
    that can be checked" must appear here as a row.

§6  DOES IT ADD UP?
    What §5 would predict, against what §1 actually shows.
    CLOSES / DOES NOT CLOSE / NOT APPLICABLE.
    If it does not close, give every honest reading. Do not pick one.
    Obey rule 4: a pair you marked NO or CANNOT TELL stays uncompared here.

§7  EXPLANATION
    The causal story. Use only D numbers from §5. Add no new claims."""


@dataclass(frozen=True, slots=True)
class Instructions:
    name: str
    header: str
    closing: str


def _numbers(text: str) -> list[int]:
    return sorted({int(found) for found in re.findall(r"§(\d+)", text)})


def _instructions(name: str, sections: str) -> Instructions:
    listed = ", ".join(f"§{number}" for number in _numbers(sections))

    header = "\n\n".join((_PREAMBLE, _RULES, _LABELS, f"OUTPUT\n\n{sections}"))
    closing = (
        f"Now write the report. Write these sections, in this order:\n{listed}\n\n"
        "Cite with a part id and an exact quote. Never write a line number.\n"
        "Write NONE for any section with nothing to report.\n\n"
        "Where a section tells you to walk a part list, every id in that list "
        "gets its own line, in order, including ids whose text was not sent to "
        "you. Count the ids in the list and write that many lines. Most lines "
        "will say nothing, and that is the expected result."
    )
    return Instructions(name, header, closing)


FULL = _instructions("full", _FULL_SECTIONS)
CORE = _instructions("core", _CORE_SECTIONS)
