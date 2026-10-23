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


class CheckTask(TypedDict):
    sides: Any
    claim: Claim


def make_check_node(
    search_one: Callable[[Any, Query], Chunks],
    check: Callable[[Claim, Chunks], Finding],
) -> Callable[[CheckTask], dict[str, list[Finding]]]:
    def check_node(task: CheckTask) -> dict[str, list[Finding]]:
        claim = task["claim"]
        found = search_one(task["sides"], Query(EVIDENCE_SIDE, claim.text))
        evidence = found[:EVIDENCE_PARTS]
        if not evidence:
            return {"findings": [Finding(claim, "absent", "", "", "", "not found")]}

        try:
            finding = check(claim, evidence)
        except CheckError as exc:
            logger.warning("a claim could not be checked: %s", exc)
            finding = Finding(claim, UNCHECKED, "", "", "", "no tier could check it")
        return {"findings": [finding]}

    return check_node
