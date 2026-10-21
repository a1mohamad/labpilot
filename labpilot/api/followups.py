import logging
from collections.abc import Callable

from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult
from labpilot.prompts import (
    FOLLOW_UP_MAX_TOKENS,
    FOLLOW_UP_VERSION,
    build_follow_up_prompt,
    follow_up_problem,
    last_answer_excerpt,
)

logger = logging.getLogger(__name__)


def last_answer_text(result: LLMResult) -> str:
    return last_answer_excerpt(result.text)


def make_rewriter(client: LLMClient) -> Callable[[str, list[str], str], str]:
    def rewriter(question: str, history: list[str], last_answer: str) -> str:
        def problem_with(result: LLMResult) -> str | None:
            return follow_up_problem(question, result.text)

        prompt = build_follow_up_prompt(question, history, last_answer)
        try:
            result = client.generate(
                prompt,
                max_tokens=FOLLOW_UP_MAX_TOKENS,
                problem_with=problem_with,
            )
        except AllFreeTiersExhausted:
            # A rewrite only helps. When no tier gives a good one, the question
            # goes on as the person wrote it, and the answer is still written.
            logger.warning("no tier could rewrite the follow-up", exc_info=True)
            return question

        logger.info(
            "follow-up v%d rewritten by %s (tier %d)",
            FOLLOW_UP_VERSION,
            result.model,
            result.tier,
        )
        return result.text

    return rewriter
