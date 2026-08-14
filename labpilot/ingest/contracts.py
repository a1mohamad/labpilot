from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Side = Literal["A", "B"]


@dataclass(frozen=True, slots=True)
class Piece:
    text: str
    start_line: int
    end_line: int
    label: str = ""


@dataclass(frozen=True, slots=True)
class Chunk:
    text: str
    source: str
    start_line: int
    end_line: int
    side: Side
    artifact_id: str
    chunk_index: int
    header: str = ""
    embedding_model: str | None = None
    dim: int | None = None

    def __post_init__(self) -> None:
        if self.side not in ("A", "B"):
            raise ValueError(f"side must be 'A' or 'B', got {self.side!r}")

    @property
    def embed_text(self) -> str:
        return f"{self.header}\n{self.text}" if self.header else self.text
