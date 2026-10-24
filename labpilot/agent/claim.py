from dataclasses import dataclass

# A claim about how the work is done is checked against the other file. A claim
# that only reports a result is kept and never checked: the other file cannot
# show it, and its checks were noise (section 25.6).
METHOD = "method"
RESULT = "result"
CLAIM_KINDS = (METHOD, RESULT)


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    source: str
    quote: str
    kind: str = METHOD
