from collections.abc import Callable

import psycopg

from labpilot.api.errors import GenerationUnavailable, StorageUnavailable
from labpilot.api.file_parts import read_parts
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import SUMMARY_MAX_TOKENS, build_summary_prompt


def make_summarizer(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str], str]:
    def summarize(artifact_id: str) -> str:
        read = read_parts(conn, artifact_id, limit=None, error=StorageUnavailable)
        prompt = build_summary_prompt(read.texts)

        try:
            return client.generate(prompt, max_tokens=SUMMARY_MAX_TOKENS).text
        except AllFreeTiersExhausted as exc:
            raise GenerationUnavailable(
                "every free tier failed", attempts=exc.attempts
            ) from exc

    return summarize
