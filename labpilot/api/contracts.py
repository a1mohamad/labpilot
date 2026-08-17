from __future__ import annotations

from pydantic import BaseModel


class AttemptOut(BaseModel):
    tier: int
    model: str
    error: str


class SideChunks(BaseModel):
    total: int
    sent: int


class CitationOut(BaseModel):
    chunk_id: str
    quote: str
    source: str
    line: int
    text: str
    unique: bool


class CitationReport(BaseModel):
    written: int
    resolved: int
    resolved_list: list[CitationOut]


class CompareResponse(BaseModel):
    answer: str
    model: str
    tier: int
    finish_reason: str
    attempts: list[AttemptOut]
    chunks: dict[str, SideChunks]
    citations: CitationReport


class ExhaustedDetail(BaseModel):
    message: str
    attempts: list[AttemptOut]
