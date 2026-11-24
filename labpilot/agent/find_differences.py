from collections.abc import Callable, Sequence
from functools import partial
from typing import TypedDict

from labpilot.agent._safety_net import or_nothing
from labpilot.agent.claim import METHOD
from labpilot.agent.difference import Difference
from labpilot.agent.errors import DifferencesError
from labpilot.agent.state import State

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
        run = partial(find, task["a"], task["b"], task["facts"])
        return {"differences": or_nothing(run, DifferencesError, "differences")}

    return find_differences_node
