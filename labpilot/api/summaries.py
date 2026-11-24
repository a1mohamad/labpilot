import logging
from collections.abc import Callable

import psycopg

from labpilot.api.answering import generate
from labpilot.api.chains import for_task
from labpilot.api.errors import ApiError, GenerationUnavailable, StorageUnavailable
from labpilot.api.file_parts import read_parts
from labpilot.api.saved import SavedResults, saved_summary
from labpilot.llm import LLMClient
from labpilot.prompts import SUMMARY_MAX_TOKENS, build_summary_prompt

logger = logging.getLogger(__name__)


def summary_chain(client: LLMClient) -> LLMClient:
    """Return the client for the summary route."""
    return for_task(client, "summary")


def make_summarizer(
    conn: psycopg.Connection, client: LLMClient
) -> Callable[[str], str]:
    def summarize(artifact_id: str) -> str:
        read = read_parts(conn, artifact_id, limit=None, error=StorageUnavailable)
        prompt = build_summary_prompt(read.texts)
        return generate(client, prompt, max_tokens=SUMMARY_MAX_TOKENS).text

    return summarize


def or_no_summary(summarize: Callable[[str], str]) -> Callable[[str], str]:
    """The same summary, or "" when every tier failed.

    A summary is a guide, not the evidence, so the report is still written, from
    the parts alone.
    """

    def softly(artifact_id: str) -> str:
        try:
            return summarize(artifact_id)
        except GenerationUnavailable:
            logger.warning(
                "no summary of %s: every tier failed", artifact_id, exc_info=True
            )
            return ""

    return softly


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
    summarize = saved_summary(saved, make_summarizer(conn, summary_chain(client)))
    try:
        summarize(artifact_id)
    except (ApiError, psycopg.Error):
        logger.warning("no summary of %s after the upload", artifact_id, exc_info=True)
        return False

    return True
