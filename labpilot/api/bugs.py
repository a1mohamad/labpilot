import logging
from collections.abc import Callable

import psycopg

from labpilot.agent import Bug, BugsError, merge_bugs
from labpilot.api.bug_hunt import find_suspects
from labpilot.api.bug_skeptic import judge_suspects, parses
from labpilot.api.file_parts import read_parts
from labpilot.llm import LLMClient
from labpilot.prompts import BUGS_SCAN_TOKENS, BUGS_VERSION

logger = logging.getLogger(__name__)


def make_bug_finder(
    conn: psycopg.Connection,
    *,
    client: LLMClient,
    skeptic_client: LLMClient,
    trace_client: LLMClient,
) -> Callable[[str, str], tuple[Bug, ...]]:
    """The defects of one file, read alone (section 29, D87 to D95).

    Three steps: find the suspects (three hunts and a checklist audit), drop
    the repeats and the syntax claims the code disproves, then let the skeptic
    judge the rest.
    """

    def find(artifact_id: str, summary: str) -> tuple[Bug, ...]:
        parts = read_parts(conn, artifact_id, limit=BUGS_SCAN_TOKENS, error=BugsError)
        found = find_suspects(parts, summary, client=client, trace_client=trace_client)
        suspects = [bug for bug in merge_bugs(found) if not parses(bug)]
        logger.info(
            "bugs v%d: %d suspects, %d after repeats and syntax claims",
            BUGS_VERSION,
            len(found),
            len(suspects),
        )
        return judge_suspects(parts, suspects, skeptic_client)

    return find
