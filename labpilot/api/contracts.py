from __future__ import annotations

from dataclasses import dataclass

from labpilot.ingest import Chunk
from labpilot.llm import LLMResult
from labpilot.store import ArtifactRecord


@dataclass(frozen=True, slots=True)
class Artifact:
    name: str
    raw: bytes


@dataclass(frozen=True, slots=True)
class Comparison:
    result: LLMResult
    chunks: tuple[Chunk, ...]
    selected: tuple[Chunk, ...]
    prompt: str

    # How many chunks each side really HOLDS, when that is more than we read.
    # None on the stuff path, where `chunks` already is the whole corpus.
    #
    # Without it the response counts what retrieval returned and calls it the
    # total, so a 120-chunk file reports "25 of 25" and the count that exists
    # to prove the file was read becomes a claim that it was read whole.
    totals: dict[str, int] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Ingested:
    artifact: ArtifactRecord
    chunks: int
    embedding_minutes: float
