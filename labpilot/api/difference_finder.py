import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import psycopg

from labpilot.agent import Difference, DifferencesError, merged_findings
from labpilot.api.difference_audit import run_audit
from labpilot.api.difference_review import Merge, finding_line, judge
from labpilot.api.difference_scan import run_scan
from labpilot.api.file_parts import read_parts
from labpilot.llm import LLMClient
from labpilot.prompts import (
    AUDIT_VERSION,
    DIFFERENCES_READ_TOKENS,
    REVIEW_VERSION,
    SCAN_A_TEXT_TOKENS,
    SCAN_VERSION,
)
from labpilot.timing import in_this_context

logger = logging.getLogger(__name__)


def make_find_differences(
    conn: psycopg.Connection,
    *,
    whole: LLMClient,
    small: LLMClient,
    merge: Merge,
) -> Callable[[str, str, Sequence[str]], tuple[Difference, ...]]:
    """The differences between A and B (section 29.9, D96 to D98).

    `whole` makes the calls that read big groups of B (the audit and the
    judge), `small` the many calls on small groups (the scan), and `merge`
    groups the findings that make the same point.
    """

    def find(a_id: str, b_id: str, facts: Sequence[str]) -> tuple[Difference, ...]:
        a = read_parts(conn, a_id, limit=None, error=DifferencesError)
        b = read_parts(
            conn, b_id, limit=DIFFERENCES_READ_TOKENS, error=DifferencesError
        )
        # The scan reads what A states: A's own text when it is small, else its
        # list of facts. A that is too big and has no facts cannot be compared.
        reference = a.text if a.tokens <= SCAN_A_TEXT_TOKENS else "\n".join(facts)
        if not reference.strip():
            raise DifferencesError("A is too big to read and has no list of facts")

        # The audit (A to B) and the scan (B to A) do not need each other, so
        # they run at the same time.
        with ThreadPoolExecutor(2) as pool:
            audit = (
                pool.submit(in_this_context(run_audit), whole, facts, b)
                if facts
                else None
            )
            scan = pool.submit(in_this_context(run_scan), small, reference, b)
            audited, audit_answered = audit.result() if audit else ([], False)
            scanned, scan_answered = scan.result()
        if not (audit_answered or scan_answered):
            raise DifferencesError("no tier answered the audit or the scan")

        found = [
            replace(d, evidence=b.chunk_for(d.source)) for d in [*audited, *scanned]
        ]
        kept = judge(whole, found, b, reference) if found else []
        groups = merge({n: finding_line(d) for n, d in enumerate(kept)})
        shown = merged_findings(kept, groups)
        logger.info(
            "differences (audit v%d, scan v%d, review v%d): %d found, "
            "%d kept by the judges, %d after the merge",
            AUDIT_VERSION,
            SCAN_VERSION,
            REVIEW_VERSION,
            len(found),
            len(kept),
            len(shown),
        )
        return tuple(shown)

    return find
