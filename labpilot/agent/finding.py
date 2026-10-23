from dataclasses import dataclass

from labpilot.agent.claim import Claim

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
