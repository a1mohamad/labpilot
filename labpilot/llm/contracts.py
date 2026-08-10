from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Attempt:

    tier: int
    model:str
    error:str

@dataclass(frozen=True, slots=True)
class LLMResult:
    text:str
    tier: int
    model: str
    attempts: tuple[Attempt, ...] = ()
