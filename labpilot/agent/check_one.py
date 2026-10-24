import logging
from collections.abc import Callable
from typing import Any, TypedDict

from labpilot.agent.claim import Claim
from labpilot.agent.errors import CheckError
from labpilot.agent.finding import UNCHECKED, Finding
from labpilot.agent.plan import Query
from labpilot.agent.state import Chunks

logger = logging.getLogger(__name__)

# The claims come from A, so the evidence is searched in B. This many parts go
# to the check: a claim is one fact, and six parts are about 2,000 tokens.
EVIDENCE_SIDE = "B"
EVIDENCE_PARTS = 6

# A claim that is "absent" is searched again with a new query, at most this many
# times. It is the only loop in the graph, so this number is its hard stop.
MAX_RETRIES = 2

# (claim, the queries tried so far, what the last check said) -> a new query.
# None means that no new query could be written.
NewQuery = Callable[[Claim, tuple[str, ...], str], str | None]


class CheckTask(TypedDict):
    sides: Any
    claim: Claim


def make_check_node(
    search_one: Callable[[Any, Query], Chunks],
    check: Callable[[Claim, Chunks], Finding],
    new_query: NewQuery | None = None,
) -> Callable[[CheckTask], dict[str, list[Finding]]]:
    def judge(task: CheckTask, query: str) -> Finding:
        found = search_one(task["sides"], Query(EVIDENCE_SIDE, query))
        evidence = found[:EVIDENCE_PARTS]
        if not evidence:
            return Finding(task["claim"], "absent", "", "", "", "nothing found")
        return check(task["claim"], evidence)

    def check_node(task: CheckTask) -> dict[str, list[Finding]]:
        claim = task["claim"]
        tried = [claim.text]
        finding: Finding | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                finding = judge(task, tried[-1])
            except CheckError as exc:
                logger.warning("a claim could not be checked: %s", exc)
                # An "absent" from an earlier search says more than "unchecked".
                if finding is None:
                    finding = Finding(
                        claim, UNCHECKED, "", "", "", "no tier could check it"
                    )
                break

            retries_left = MAX_RETRIES - attempt
            if finding.verdict != "absent" or new_query is None or retries_left == 0:
                break
            query = new_query(claim, tuple(tried), finding.note)
            if query is None:
                break
            tried.append(query)

        if len(tried) > 1:
            logger.info(
                "a claim was searched %d times, %s: %s",
                len(tried),
                finding.verdict,
                tried[1:],
            )
        return {"findings": [finding]}

    return check_node
