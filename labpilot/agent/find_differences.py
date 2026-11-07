import logging
from collections.abc import Callable, Sequence
from typing import TypedDict

from labpilot.agent.claim import METHOD
from labpilot.agent.difference import Difference
from labpilot.agent.errors import DifferencesError
from labpilot.agent.state import State

logger = logging.getLogger(__name__)

STEP = "find_differences"

FindDifferences = Callable[[str, str, Sequence[str]], tuple[Difference, ...]]


class DifferencesTask(TypedDict):
    a: str
    b: str
    facts: tuple[str, ...]


def wants_differences(state: State) -> bool:
    has_both = bool(state.get("a") and state.get("b"))
    return has_both and STEP in state["plan"].steps


def differences_task(state: State) -> DifferencesTask:
    claims = state.get("claims", ())
    facts = tuple(claim.text for claim in claims if claim.kind == METHOD)
    return {"a": state["a"], "b": state["b"], "facts": facts}


def make_find_differences_node(
    find: FindDifferences,
) -> Callable[[DifferencesTask], dict[str, list[Difference]]]:
    def find_differences_node(task: DifferencesTask) -> dict[str, list[Difference]]:
        # A safety net: when it fails, the answer goes on without it.
        try:
            found = find(task["a"], task["b"], task["facts"])
        except DifferencesError as exc:
            logger.warning("no differences, the answer goes on: %s", exc)
            found = ()
        return {"differences": list(found)}

    return find_differences_node
