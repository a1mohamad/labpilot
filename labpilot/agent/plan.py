from dataclasses import dataclass

from labpilot.ingest import Side


@dataclass(frozen=True, slots=True)
class Query:
    side: Side
    text: str


@dataclass(frozen=True, slots=True)
class Plan:
    steps: tuple[str, ...]
    queries: tuple[Query, ...]
