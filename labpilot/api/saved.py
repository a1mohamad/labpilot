"""D104: the claims, differences and bugs of some files, made once and reused.

They depend on the files and the instruction versions, not on the question
(the claims do not read the question, R3). So the next message, or the next
chat with the same files, reads them from the database instead of running the
audit and the bug hunt again. The key names the step, the files and the
versions, so a new instruction never answers from an old result.

A database error here never stops the answer: a result that cannot be read is
made again, and one that cannot be saved is still used.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any

import psycopg

from labpilot.agent import METHOD, Bug, Claim, Difference, Plan
from labpilot.api.checkpoints import SERDE
from labpilot.prompts import (
    AUDIT_VERSION,
    BUGS_VERSION,
    CLAIMS_VERSION,
    FRESH_VERSION,
    REVIEW_VERSION,
    SCAN_VERSION,
)
from labpilot.store import StoreError, read_saved, write_saved

logger = logging.getLogger(__name__)

CLAIMS = "claims"
DIFFERENCES = "differences"
BUGS = "bugs"
FRESH = "fresh"


def claims_key(a: str) -> str:
    return f"{CLAIMS}:{a}:v{CLAIMS_VERSION}"


def differences_key(a: str, b: str, facts: Sequence[str]) -> str:
    # The facts come from the saved claims, so the same files give the same
    # facts and the same key. Other facts (a new claims version) give a new key.
    digest = hashlib.sha256("\n".join(facts).encode("utf-8")).hexdigest()[:16]
    versions = f"a{AUDIT_VERSION}s{SCAN_VERSION}r{REVIEW_VERSION}"
    return f"{DIFFERENCES}:{a}:{b}:{versions}:{digest}"


def bugs_key(b: str) -> str:
    return f"{BUGS}:{b}:v{BUGS_VERSION}"


def fresh_key(b: str, question: str) -> str:
    # The same question about the same file asks the same thing; the audit
    # version and the wording version are in the key like the other steps.
    digest = hashlib.sha256(question.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{FRESH}:{b}:a{AUDIT_VERSION}f{FRESH_VERSION}:{digest}"


class SavedResults:
    """The saved results of one message: what was reused and what was made."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn
        self.reused: list[str] = []
        self.made: list[str] = []
        self._lock = threading.Lock()

    def read(self, key: str) -> Any | None:
        try:
            found = read_saved(self.conn, key)
        except (StoreError, psycopg.Error):
            logger.warning("could not read the saved %s", key, exc_info=True)
            return None
        if found is None:
            return None
        try:
            return SERDE.loads_typed(found)
        except Exception:  # noqa: BLE001 - a bad row is made again, never fatal
            logger.warning("could not read back the saved %s", key, exc_info=True)
            return None

    def get_or_make(
        self,
        step: str,
        key: str,
        artifacts: tuple[str, ...],
        make: Callable[[], tuple[Any, ...]],
    ) -> tuple[Any, ...]:
        saved = self.read(key)
        if saved is not None:
            with self._lock:
                self.reused.append(step)
            logger.info("%s read from the saved %s", step, key)
            return tuple(saved)

        value = make()
        try:
            kind, payload = SERDE.dumps_typed(tuple(value))
            write_saved(self.conn, key, kind, payload, artifacts=artifacts)
        except (StoreError, psycopg.Error):
            logger.warning("could not save %s", key, exc_info=True)
        with self._lock:
            self.made.append(step)
        return value

    def has(self, key: str) -> bool:
        return self.read(key) is not None


def saved_claims(
    saved: SavedResults, extract: Callable[[str], tuple[Claim, ...]]
) -> Callable[[str], tuple[Claim, ...]]:
    def claims(a: str) -> tuple[Claim, ...]:
        return saved.get_or_make(CLAIMS, claims_key(a), (a,), lambda: extract(a))

    return claims


def saved_differences(
    saved: SavedResults,
    find: Callable[[str, str, Sequence[str]], tuple[Difference, ...]],
) -> Callable[[str, str, Sequence[str]], tuple[Difference, ...]]:
    def differences(a: str, b: str, facts: Sequence[str]) -> tuple[Difference, ...]:
        key = differences_key(a, b, facts)
        return saved.get_or_make(DIFFERENCES, key, (a, b), lambda: find(a, b, facts))

    return differences


def saved_bugs(
    saved: SavedResults, find: Callable[[str, str], tuple[Bug, ...]]
) -> Callable[[str, str], tuple[Bug, ...]]:
    def bugs(artifact: str, summary: str) -> tuple[Bug, ...]:
        key = bugs_key(artifact)
        return saved.get_or_make(
            BUGS, key, (artifact,), lambda: find(artifact, summary)
        )

    return bugs


def saved_fresh(
    saved: SavedResults, check: Callable[[str, str], tuple[Difference, ...]]
) -> Callable[[str, str], tuple[Difference, ...]]:
    def fresh(question: str, b: str) -> tuple[Difference, ...]:
        return saved.get_or_make(
            FRESH, fresh_key(b, question), (b,), lambda: check(question, b)
        )

    return fresh


def with_saved_steps(
    saved: SavedResults, plan: Callable[[str, str, str], Plan]
) -> Callable[[str, str, str], Plan]:
    """A step whose result is already saved costs nothing, so it is always run.

    A follow-up such as "explain the second difference" may be planned with no
    step at all; then the answer would not see the saved findings. So a saved
    bug hunt adds `find_bugs`, and saved differences add `find_differences`.
    """

    def planned(question: str, a: str, b: str) -> Plan:
        made = plan(question, a, b)
        steps = list(made.steps)
        if b and "find_bugs" not in steps and saved.has(bugs_key(b)):
            steps.append("find_bugs")
        if a and b and "find_differences" not in steps:
            claims = saved.read(claims_key(a))
            if claims is not None:
                facts = [c.text for c in claims if c.kind == METHOD]
                if saved.has(differences_key(a, b, facts)):
                    steps.append("find_differences")
        if steps == list(made.steps):
            return made
        return replace(made, steps=tuple(steps))

    return planned
