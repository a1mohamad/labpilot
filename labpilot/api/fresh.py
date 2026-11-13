import logging
from dataclasses import replace

import psycopg

from labpilot.agent import Difference, DifferencesError, FreshCheck
from labpilot.api.difference_audit import run_audit
from labpilot.api.file_parts import read_parts
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import (
    DIFFERENCES_READ_TOKENS,
    FRESH_MAX_TOKENS,
    FRESH_VERSION,
    build_fresh_claim_prompt,
)

logger = logging.getLogger(__name__)


def make_fresh_check(
    conn: psycopg.Connection, *, whole: LLMClient, small: LLMClient
) -> FreshCheck:
    """ONE new check of B for a question the first analysis did not cover.

    The question becomes one statement (one small call), and the audit that
    already checks A's facts checks that statement against all of B. The finding
    is NOT a fact of A, so its `fact` is cleared and its text says which
    question it answers.
    """

    def check(question: str, b_id: str) -> tuple[Difference, ...]:
        b = read_parts(
            conn, b_id, limit=DIFFERENCES_READ_TOKENS, error=DifferencesError
        )
        try:
            claim = small.generate(
                build_fresh_claim_prompt(question), max_tokens=FRESH_MAX_TOKENS
            ).text.strip()
        except AllFreeTiersExhausted as exc:
            raise DifferencesError("no tier could state the question") from exc
        if not claim:
            raise DifferencesError("the question became an empty statement")

        found, answered = run_audit(whole, [claim], b)
        if not answered:
            raise DifferencesError("no tier answered the new check")
        logger.info(
            "new check v%d: %r -> %d finding(s)", FRESH_VERSION, claim, len(found)
        )
        return tuple(
            replace(
                d,
                fact="",
                text=f'Asked "{question}": {d.text}',
                evidence=b.chunk_for(d.source),
            )
            for d in found
        )

    return check
