from dataclasses import dataclass

from labpilot.agent.claim import Claim
from labpilot.ingest import Chunk

# "unchecked" is not a verdict the model can give. It is what a claim gets when
# no tier could check it, so the report says so instead of losing the claim.
UNCHECKED = "unchecked"


@dataclass(frozen=True, slots=True)
class Finding:
    claim: Claim
    verdict: str
    kind: str
    source: str
    quote: str
    note: str
    # The part of the other file that decided a match or a mismatch, so the
    # answer can be shown the code itself and not only one quoted line (R20).
    evidence: Chunk | None = None
