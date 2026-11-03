from dataclasses import dataclass

from labpilot.ingest import Chunk

# What A says about a code finding when A does not mention it at all.
A_SILENT = "A does not say"


@dataclass(frozen=True, slots=True)
class CodeFinding:
    """Something B does that A does otherwise or never says (the find_missing step).

    `text` is the finding in plain words, `source` and `quote` place it in B,
    `a_says` is A's own words about it or A_SILENT, `evidence` is the part of B
    that shows it, so the answer can be shown the code itself, and `topic` is a
    few words that name it, so the same thing seen in two groups is kept once.
    """

    text: str
    source: str
    quote: str
    a_says: str
    evidence: Chunk | None = None
    topic: str = ""
