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


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchHit:
    chunk_index: int
    text: str
    source: str
    start_line: int
    end_line: int
    score: float
    header: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredChunk:
    """One chunk read back, with neither a vector nor a score.

    NOT a ChunkRecord and NOT a SearchHit, deliberately. ChunkRecord carries
    the vector, which is the one thing the stuff path must never fetch - it is
    the ~14MB this whole design exists to avoid. SearchHit carries a score, and
    nothing scored these rows; filling it with 1.0 would be fiction, the same
    argument that kept the embedder out of HTTPProvider.
    """

    chunk_index: int
    text: str
    source: str
    start_line: int
    end_line: int
    header: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredArtifact:
    """What one artifact IS, and how big, in a single round trip.

    `characters` is the total length of every chunk's embed_text - the exact
    string ingest measured. store/ deliberately does NOT convert that to
    tokens: CHARS_PER_TOKEN belongs to tokens.py, and a second copy of it here
    is a number that can drift away from the one the prompt layer uses.
    """

    artifact: ArtifactRecord
    chunks: int
    characters: int
