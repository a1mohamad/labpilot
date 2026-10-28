import logging
from collections.abc import Callable
from typing import TypedDict

from labpilot.agent.code_finding import CodeFinding
from labpilot.agent.errors import DifferencesError
from labpilot.agent.state import State

logger = logging.getLogger(__name__)

STEP = "find_missing"


class MissingTask(TypedDict):
    a: str
    b: str


def wants_missing(state: State) -> bool:
    return STEP in state["plan"].steps


def make_find_missing_node(
    find: Callable[[str, str], tuple[CodeFinding, ...]],
) -> Callable[[MissingTask], dict[str, list[CodeFinding]]]:
    def find_missing_node(task: MissingTask) -> dict[str, list[CodeFinding]]:
        # A safety net, like the claims: when it fails, the answer goes on.
        try:
            found = find(task["a"], task["b"])
        except DifferencesError as exc:
            logger.warning("no code findings, the answer goes on: %s", exc)
            found = ()
        return {"code_findings": list(found)}

    return find_missing_node
