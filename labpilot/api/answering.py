from __future__ import annotations

from collections.abc import Callable

from labpilot.api.chains import for_task
from labpilot.api.errors import GenerationUnavailable
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, routes

# The route of the answer, by how many files the question has.
ANSWER_TASKS = ("respond_chat", "respond_one", "respond_two")


def generate(client: LLMClient, prompt: str, *, max_tokens: int) -> LLMResult:
    """The text of one model, or the API's own error when every tier failed."""
    try:
        return client.generate(prompt, max_tokens=max_tokens)
    except AllFreeTiersExhausted as exc:
        raise GenerationUnavailable(
            "every free tier failed", attempts=exc.attempts
        ) from exc


def answerer(client: LLMClient, files: int) -> Callable[[str], LLMResult]:
    """The function that writes the answer to a question about `files` files."""
    task = ANSWER_TASKS[min(files, 2)]
    routed = for_task(client, task)
    max_tokens = routes.TASKS[task].max_tokens

    def answer(prompt: str) -> LLMResult:
        return generate(routed, prompt, max_tokens=max_tokens)

    return answer
