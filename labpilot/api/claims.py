import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import psycopg

from labpilot.agent import (
    CLAIMS_TOOL_NAME,
    Claim,
    ClaimsError,
    claims_schema,
    join_claims,
    read_claims,
)
from labpilot.api.errors import UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.prompts import (
    CLAIMS_MAX_TOKENS,
    CLAIMS_VERSION,
    build_claims_prompt,
    claims_fit,
    claims_groups,
)
from labpilot.store import UnknownArtifact, read_chunks

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "List the checkable facts that the reference states."

# The groups are asked at the same time, at most this many at once.
CLAIMS_AT_ONCE = 4


def _claims_problem(
    result: LLMResult, *, sources: Sequence[str], texts: Sequence[str]
) -> str | None:
    if result.arguments is None:
        return "no arguments"
    try:
        read_claims(result.arguments, sources, texts)
    except ClaimsError as exc:
        return str(exc)
    return None


def make_claims_extractor(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str], tuple[Claim, ...]]:
    tool = Tool(
        name=CLAIMS_TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters=claims_schema(),
    )

    def one_group(parts: list[str], sources: list[str]) -> tuple[Claim, ...] | None:
        try:
            result = client.generate(
                build_claims_prompt(parts),
                max_tokens=CLAIMS_MAX_TOKENS,
                tool=tool,
                problem_with=partial(_claims_problem, sources=sources, texts=parts),
            )
        except AllFreeTiersExhausted as exc:
            logger.warning("no tier gave claims for a group (%d)", len(exc.attempts))
            return None
        if result.arguments is None:
            logger.warning("%s gave no arguments for a group", result.model)
            return None

        claims = read_claims(result.arguments, sources, parts)
        logger.info(
            "claims v%d made by %s (tier %s): %d claims from %d parts",
            CLAIMS_VERSION,
            result.model,
            result.tier,
            len(claims),
            len(parts),
        )
        return claims

    def extract(artifact_id: str) -> tuple[Claim, ...]:
        try:
            stored = read_chunks(conn, artifact_id)
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc

        parts = [f"{chunk.header}\n{chunk.text}" for chunk in stored]
        if not parts:
            raise ClaimsError("the reference has no parts")
        if not claims_fit(parts):
            raise ClaimsError(
                f"the reference has {len(parts)} parts and is too big to read whole"
            )
        # The model gives a part NUMBER and the code looks up the place, because
        # a model copies a number far more reliably than a file name and lines.
        sources = [chunk.header or chunk.source for chunk in stored]
        groups = claims_groups(parts)

        with ThreadPoolExecutor(min(len(groups), CLAIMS_AT_ONCE)) as pool:
            answers = list(
                pool.map(
                    lambda ids: one_group(
                        [parts[i] for i in ids], [sources[i] for i in ids]
                    ),
                    groups,
                )
            )

        given = [answer for answer in answers if answer is not None]
        if not given:
            raise ClaimsError(f"no tier gave claims for any of {len(groups)} groups")
        if len(given) < len(groups):
            logger.warning(
                "claims of %d of %d groups are missing",
                len(groups) - len(given),
                len(groups),
            )
        return join_claims(given)

    return extract
