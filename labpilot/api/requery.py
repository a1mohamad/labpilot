import logging
from collections.abc import Callable

from labpilot.agent import Claim
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult
from labpilot.prompts import (
    REQUERY_MAX_TOKENS,
    REQUERY_VERSION,
    build_requery_prompt,
    requery_problem,
)

logger = logging.getLogger(__name__)


def make_query_writer(
    client: LLMClient,
) -> Callable[[Claim, tuple[str, ...], str], str | None]:
    def new_query(claim: Claim, tried: tuple[str, ...], note: str) -> str | None:
        def problem_with(result: LLMResult) -> str | None:
            return requery_problem(tried, result.text)

        prompt = build_requery_prompt(claim.text, tried, note)
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
