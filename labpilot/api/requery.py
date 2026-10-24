import logging
from collections.abc import Callable
from typing import Any

from labpilot.agent import Claim
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult
from labpilot.prompts import (
    REQUERY_MAX_TOKENS,
    REQUERY_VERSION,
    build_requery_prompt,
    requery_problem,
)

logger = logging.getLogger(__name__)


def _artifact_id(sides: Any) -> str | None:
    for stored in (sides or {}).values():
        artifact = getattr(stored, "artifact", None)
        if artifact is not None:
            return artifact.id
    return None


def make_query_writer(
    client: LLMClient,
    outline: Callable[[str], str] | None = None,
) -> Callable[[Claim, tuple[str, ...], str, Any], str | None]:
    def new_query(
        claim: Claim, tried: tuple[str, ...], note: str, sides: Any = None
    ) -> str | None:
        def problem_with(result: LLMResult) -> str | None:
            return requery_problem(tried, result.text)

        # The names the other file really uses (R17).
        artifact_id = _artifact_id(sides)
        shown = outline(artifact_id) if outline and artifact_id else ""
        prompt = build_requery_prompt(claim.text, tried, note, shown)
        try:
            result = client.generate(
                prompt,
                max_tokens=REQUERY_MAX_TOKENS,
                problem_with=problem_with,
            )
        except AllFreeTiersExhausted:
            # A new query only helps. When no tier writes a good one, the claim
            # stays as the first search left it.
            logger.warning("no tier could write a new query", exc_info=True)
            return None

        logger.info(
            "query v%d by %s (tier %d): %s",
            REQUERY_VERSION,
            result.model,
            result.tier,
            result.text.strip(),
        )
        return result.text.strip()

    return new_query
