from collections.abc import Sequence

from labpilot._text import truncate
from labpilot.prompts.instructions import Instructions

# The wording below is FIXED. Change it only together with this number, which is
# logged beside every new query.
REQUERY_VERSION = 1

# One short line, but a tier that thinks spends tokens first, so this is only a
# backstop.
REQUERY_MAX_TOKENS = 2_000

# A query is a few key words. Anything longer is a sentence, and a sentence is
# what the first search already used.
MAX_QUERY_CHARS = 200
EARLIER_CHARS = 200
NOTE_CHARS = 300

REQUERY = Instructions(
    name="requery",
    header="""\
A reference says how some work was done. One claim from the reference was looked
for in the other file with a search, and the parts that came back do not show it.

Write ONE new search query for the other file.
- The other file may say the same thing in other words. Think of the names it
  could use for this value, setting or step: the names in its code and in its
  comments, and the short words around them.
- Use a few key words, not a sentence.
- Do not repeat an earlier query, and do not only change the order of its words.
- Write the query on one line and nothing else: no quotes, no explanation.

Example.
Claim: the mesh has 200 cells
Earlier queries: 1. the mesh has 200 cells
What the check said: the parts are about the output format
Answer: n_cells num_cells nx grid size""",
    closing="Write the new query now.",
)


def build_requery_prompt(claim: str, tried: Sequence[str], note: str = "") -> str:
    if not claim.strip():
        raise ValueError("a new query needs a claim")
    if not tried:
        raise ValueError("a new query needs the queries that we already tried")

    earlier = "\n".join(
        f"{number}. {truncate(text, EARLIER_CHARS)}"
        for number, text in enumerate(tried, start=1)
    )
    blocks = [
        REQUERY.header,
        f"THE CLAIM\n{claim.strip()}",
        f"EARLIER QUERIES\n{earlier}",
    ]
    if note.strip():
        blocks.append(f"WHAT THE CHECK SAID\n{truncate(note, NOTE_CHARS)}")
    blocks.append(REQUERY.closing)

    return "\n\n".join(blocks)


def _plain(query: str) -> str:
    return " ".join(query.split()).casefold()


def requery_problem(tried: Sequence[str], answer: str) -> str | None:
    text = answer.strip()
    if not text:
        return "the answer is blank"
    if "\n" in text:
        return "the answer has more than one line"
    if len(text) > MAX_QUERY_CHARS:
        return f"the answer is {len(text)} characters long"
    if _plain(text) in {_plain(query) for query in tried}:
        return "the answer repeats an earlier query"
    return None
