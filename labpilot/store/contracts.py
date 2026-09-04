from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Vector = tuple[float, ...]
Side = Literal["A", "B"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactRecord:
    id: str
    name: str
    side: Side
    embedding_model: str
    dim: int

    def __post_init__(self) -> None:
        if self.side not in ["A", "B"]:
            raise ValueError(f"side must be 'A' or 'B', got {self.side!r}")
        if self.dim < 1:
            raise ValueError(f"dim must be positive, got {self.dim}")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChunkRecord:
    chunk_index: int
    text: str
    source: str
    start_line: int
    end_line: int
    vector: Vector
    header: str = ""
