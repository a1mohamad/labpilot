import logging
from collections.abc import Callable, Sequence
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
from labpilot.api.file_parts import read_parts
from labpilot.api.tool_calls import ask_tool, at_once
from labpilot.llm import LLMClient, Tool
from labpilot.prompts import (
    CLAIMS_MAX_TOKENS,
    CLAIMS_VERSION,
    build_claims_prompt,
    claims_fit,
    claims_groups,
)

logger = logging.getLogger(__name__)

TOOL_DESCRIPTION = "List the checkable facts that the reference states."


def make_claims_extractor(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str], tuple[Claim, ...]]:
    tool = Tool(
        name=CLAIMS_TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters=claims_schema(),
    )

    def one_group(parts: list[str], sources: list[str]) -> tuple[Claim, ...] | None:
        claims = ask_tool(
            client,
            build_claims_prompt(parts),
            tool=tool,
            max_tokens=CLAIMS_MAX_TOKENS,
            read=partial(read_claims, sources=sources, texts=parts),
            errors=(ClaimsError,),
        )
        if claims is not None:
            logger.info(
                "claims v%d: %d claims from %d parts",
                CLAIMS_VERSION,
                len(claims),
                len(parts),
            )
        return claims

    def extract(artifact_id: str) -> tuple[Claim, ...]:
        # A dropped connection is a ClaimsError, so the answer goes on without
        # claims, like any other failure of this safety net.
        read = read_parts(conn, artifact_id, limit=None, error=ClaimsError)
        parts = list(read.texts)
        if not claims_fit(parts):
            raise ClaimsError(
                f"the reference has {len(parts)} parts and is too big to read whole"
            )
        # The model gives a part NUMBER and the code looks up the place, because
        # a model copies a number far more reliably than a file name and lines.
        sources = list(read.sources)
        groups = claims_groups(parts)

        def read_group(ids: Sequence[int]) -> tuple[Claim, ...] | None:
            return one_group([parts[i] for i in ids], [sources[i] for i in ids])

        answers = at_once(read_group, groups)
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
