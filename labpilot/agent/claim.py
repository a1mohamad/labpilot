from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    source: str
    quote: str
