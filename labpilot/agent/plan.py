from dataclasses import dataclass
from typing import Literal

from labpilot.ingest import Side


@dataclass(frozen=True, slots=True)
class Query:
    side: Side
    text: str


@dataclass(frozen=True, slots=True)
class Plan:
    steps: tuple[str, ...]
    queries: tuple[Query, ...]
    source: Literal["planner", "default"] = "planner"
    # One short question for the person, or "" (D109). The planner writes it.
    ask: str = ""
