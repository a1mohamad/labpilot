from __future__ import annotations

from pydantic import BaseModel, Field


class AttemptOut(BaseModel):
    tier: int = Field(description="Position in the fallback chain.")
    model: str = Field(description="Model that was asked and did not answer.")
    error: str = Field(description="Why that tier failed, in its own words.")


class SideChunks(BaseModel):
    total: int = Field(description="Parts the artifact was cut into.")
    sent: int = Field(description="Parts whose text reached the model.")


class CitationOut(BaseModel):
    chunk_id: str = Field(description="Part the model pointed at, e.g. B-17.")
    quote: str = Field(description="Line the model quoted, as it wrote it.")
    source: str = Field(description="File the line really lives in.")
    line: int = Field(description="Line number we counted, never the model.")
    text: str = Field(description="The line as our own copy holds it.")
    unique: bool = Field(description="False when the quote matches more than one line.")


class CompareRequest(BaseModel):
    """Two stored artifacts and a question.

    JSON, not multipart, because there are no files left to upload - that is
    the whole point of the split: ingest is paid once at POST /artifacts, and
    what crosses the wire each turn is a question.

    `question` is deliberately NOT constrained here. A blank one must come back
    through our own envelope as `invalid_question`; a min_length would make
    FastAPI answer in ITS shape instead, and a client would have to parse two
    different error formats from one endpoint.
    """

    a: str = Field(
        description="Artifact id of the reference - what SAYS what should "
        "happen. Returned by POST /artifacts.",
        examples=["A-9f2c1b7e4d3a5c60"],
    )
    b: str = Field(
        description="Artifact id of the subject - the thing that actually "
        "runs. Must be the opposite side to `a`.",
        examples=["B-3e8a04f1c927bd55"],
    )
    question: str = Field(
        description="What to ask of the pair. It steers the answer AND is the "
        "retrieval query, so re-wording it changes which parts are found.",
        examples=["Compare these and explain why the results diverge."],
    )


class CitationReport(BaseModel):
    written: int = Field(description="Citations the model wrote.")
    resolved: int = Field(description="Citations that point at real lines.")
    resolved_list: list[CitationOut] = Field(default_factory=list)


class CompareResponse(BaseModel):
    answer: str
    model: str = Field(description="Model that actually answered.")
    tier: int = Field(description="Its position in the chain.")
    finish_reason: str = Field(description="STOP is complete; MAX_TOKENS is cut.")
    attempts: list[AttemptOut] = Field(
        default_factory=list, description="Tiers that failed before this one."
    )
    chunks: dict[str, SideChunks]
    citations: CitationReport


class ErrorBody(BaseModel):
    code: str = Field(description="Stable, machine-readable identifier.")
    message: str = Field(description="Safe explanation for a human.")
    request_id: str = Field(description="Correlates this reply with the logs.")
    attempts: list[AttemptOut] = Field(
        default_factory=list, description="Only present when the chain failed."
    )


class ErrorEnvelope(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    version: str
    providers_configured: int = Field(
        description="Chain tiers whose API key is present in the environment."
    )


class RootResponse(BaseModel):
    name: str
    version: str
    docs: str


class IngestResponse(BaseModel):
    artifact_id: str = Field(description="Use this in /compare. Stable per file.")
    name: str
    side: str = Field(description="A is the reference, B is the subject.")
    chunks: int = Field(
        description="Parts stored. This is the '42 chunks' the UI shows."
    )
    embedding_model: str = Field(
        description="Every later query MUST be embedded with this same model."
    )
    embedding_minutes: float = Field(
        description="Estimate for EMBEDDING ONLY - not the time to get an answer."
    )
    slow: bool = Field(
        description="True when the caller should have warned the user first."
    )
