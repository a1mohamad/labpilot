from dataclasses import dataclass

from labpilot.ingest import Chunk

# The kinds of defect find_bugs looks for. A bug is not only code that crashes:
# the logic, the method of an experiment, the numbers and the idea itself count.
BUG_KINDS = ("code", "logic", "method", "numbers", "concept")
SEVERITIES = ("high", "low")

# What the skeptic says about a suspect.
REAL = "real"
INTENDED = "intended"
FALSE = "false"
UNCLEAR = "unclear"
# The same defect as an earlier suspect of the same batch (the vote names it).
REPEAT = "repeat"
SKEPTIC_VERDICTS = (REAL, INTENDED, FALSE, UNCLEAR, REPEAT)
# No skeptic answered: the suspect is shown, with this label.
UNCHECKED = "unchecked"


@dataclass(frozen=True, slots=True)
class Bug:
    """A defect of ONE file, found by reading it alone (the find_bugs step).

    `text` says what is wrong and what it causes, `source` and `quote` place it,
    `verdict` and `reason` are the skeptic's, and `evidence` is the part that
    shows it, so the answer can be shown the code itself.
    """

    kind: str
    text: str
    source: str
    quote: str
    severity: str = "high"
    verdict: str = UNCHECKED
    reason: str = ""
    evidence: Chunk | None = None
