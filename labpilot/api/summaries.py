import logging
from collections.abc import Callable

import psycopg

from labpilot.api.chains import bounded, for_summary
from labpilot.api.errors import ApiError, GenerationUnavailable, StorageUnavailable
from labpilot.api.file_parts import read_parts
from labpilot.api.saved import SavedResults, saved_summary
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import SUMMARY_MAX_TOKENS, build_summary_prompt

logger = logging.getLogger(__name__)

# D110: how long one model may take on a summary, and the whole call. First
# guesses; lesson 4 measures them.
SUMMARY_READ_SECONDS = 60.0
SUMMARY_TOTAL_SECONDS = 120.0


def summary_chain(client: LLMClient) -> LLMClient:
    """The short chain of cheap models for a summary, with time limits."""
    return bounded(
        for_summary(client),
        read=SUMMARY_READ_SECONDS,
        budget=SUMMARY_TOTAL_SECONDS,
        retries=0,
    )


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


def store_summary(
    conn: psycopg.Connection, client: LLMClient, artifact_id: str
) -> bool:
    """D110: make and save the summary right after a file is stored.

    It never stops the upload: when every model fails, or the database cannot
    be read, it writes a warning and returns False. Nothing is saved then, so
    the first question that needs the summary makes it. A bug in our own code
    is not caught here.
    """

    saved = SavedResults(conn)
    summarize = saved_summary(saved, make_summarizer(conn, client))
    try:
        summarize(artifact_id)
    except (ApiError, psycopg.Error):
        logger.warning("no summary of %s after the upload", artifact_id, exc_info=True)
        return False

    return True
