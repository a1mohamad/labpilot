from dataclasses import dataclass

LEAN_PREAMBLE = """\
A is the reference: it says what should happen.
B is the subject: it is the thing that actually runs.
Read B on its own first. Only then compare it with A.

Each side is a list of parts with ids like A-3 and B-17.
Anything the list does not mark as included was not sent to you."""

LEAN_RULES = """\
Cite every claim as [B-17 "one line copied exactly from that part"].
The id, one space, then one whole line in double quotes. Nothing else.
An id on its own is not a citation and is dropped, so [B-17] and [B-8, B-25]
are both wrong. Never write a line number.

Report only what could change the numbers the work reports about itself.
Leave out anything dead, cosmetic, or unable to move a result.

Two numbers may only be compared if they were produced the same way.
Two numbers from the same side and the same run are always fair to compare."""


@dataclass(frozen=True, slots=True)
class Instructions:
    name: str
    header: str
    closing: str
