from collections.abc import Callable

import psycopg

from labpilot.api.errors import GenerationUnavailable, UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import SUMMARY_MAX_TOKENS, build_summary_prompt
from labpilot.store import UnknownArtifact, read_chunks


def make_summarizer(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str], str]:
    def summarize(artifact_id: str) -> str:
        try:
            stored = read_chunks(conn, artifact_id)
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc

        parts = [f"{chunk.header}\n{chunk.text}" for chunk in stored]
        prompt = build_summary_prompt(parts)

        try:
            return client.generate(prompt, max_tokens=SUMMARY_MAX_TOKENS).text
        except AllFreeTiersExhausted as exc:
            raise GenerationUnavailable(
                "every free tier failed", attempts=exc.attempts
            ) from exc

    return summarize
