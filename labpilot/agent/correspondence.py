from dataclasses import dataclass

FULL = "FULL"
PARTIAL = "PARTIAL"
NONE = "NONE"

GATE_VERDICTS = (FULL, PARTIAL, NONE)
# Only this verdict stops the run. The other two go on to the normal answer.
HALT_VERDICT = NONE


@dataclass(frozen=True, slots=True)
class Correspondence:
    verdict: str
    reason: str
