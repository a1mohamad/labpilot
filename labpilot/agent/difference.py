from dataclasses import dataclass

from labpilot.ingest import Chunk

# What a difference between A and B can be.
DIFFERS = "differs"  # A states it and B does it differently
MISSING = "missing"  # A states a rule and B never does it
SILENT = "silent"  # B does it and A never says it
KINDS = (DIFFERS, MISSING, SILENT)

# Which request found it.
AUDIT = "audit"  # A's facts checked against B
SCAN = "scan"  # B read beside A


@dataclass(frozen=True, slots=True)
class Difference:
    """One difference between A and B, found by the audit or the scan.

    `fact` is the fact of A it is about ("" when the scan found it). `source`
    and `quote` place it in B, and `evidence` is the part of B that shows it.
    `unclear` is set when the judges did not agree that it is real.
    """

    kind: str
    text: str
    source: str
    quote: str
    fact: str = ""
    found_by: str = AUDIT
    evidence: Chunk | None = None
    unclear: bool = False
