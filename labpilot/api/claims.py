import logging
from collections.abc import Callable
from functools import partial

import psycopg

from labpilot.agent import (
    CLAIMS_TOOL_NAME,
    Claim,
    ClaimsError,
    claims_schema,
    read_claims,
)
from labpilot.api.errors import UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.prompts import (
    CLAIMS_MAX_TOKENS,
    CLAIMS_VERSION,
    build_claims_prompt,
    claims_fit,
)
from labpilot.store import UnknownArtifact, read_chunks

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "List the checkable facts that the reference states."


def _claims_problem(result: LLMResult, *, sources: list[str]) -> str | None:
    if result.arguments is None:
        return "no arguments"
    try:
        read_claims(result.arguments, sources)
    except ClaimsError as exc:
        return str(exc)
    return None


def make_claims_extractor(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str, str], tuple[Claim, ...]]:
    def extract(question: str, artifact_id: str) -> tuple[Claim, ...]:
        try:
            stored = read_chunks(conn, artifact_id)
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc

        parts = [f"{chunk.header}\n{chunk.text}" for chunk in stored]
        if not claims_fit(parts):
            raise ClaimsError(
                f"the reference has {len(parts)} parts and does not fit one call"
            )
        # The model gives a part NUMBER and the code looks up the place, because
        # a model copies a number far more reliably than a file name and lines.
        sources = [chunk.header or chunk.source for chunk in stored]
        tool = Tool(
            name=CLAIMS_TOOL_NAME,
            description=TOOL_DESCRIPTION,
            parameters=claims_schema(),
        )

        try:
            result = client.generate(
                build_claims_prompt(parts, question),
                max_tokens=CLAIMS_MAX_TOKENS,
                tool=tool,
                problem_with=partial(_claims_problem, sources=sources),
            )
        except AllFreeTiersExhausted as exc:
            raise ClaimsError(
                f"no tier gave good claims ({len(exc.attempts)})"
            ) from exc
        if result.arguments is None:
            raise ClaimsError(f"{result.model} gave no arguments")

        claims = read_claims(result.arguments, sources)
        logger.info(
            "claims v%d made by %s (tier %s): %d claims",
            CLAIMS_VERSION,
            result.model,
            result.tier,
            len(claims),
        )
        return claims

    return extract
