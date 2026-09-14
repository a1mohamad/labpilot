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


@dataclass(frozen=True, slots=True, kw_only=True)
class Ingested:
    artifact: ArtifactRecord
    chunks: int
    embedding_minutes: float
