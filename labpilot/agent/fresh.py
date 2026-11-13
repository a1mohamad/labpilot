import logging
from collections.abc import Callable
from typing import TypedDict

from labpilot.agent.difference import Difference
from labpilot.agent.errors import DifferencesError
from labpilot.agent.state import State

logger = logging.getLogger(__name__)

# (question, id of B) -> the findings of ONE new check of B (D104 path b, D107).
FreshCheck = Callable[[str, str], tuple[Difference, ...]]


class FreshTask(TypedDict):
    question: str
    b: str


def wants_fresh(state: State) -> bool:
    plan = state["plan"]
    return bool(plan.fresh and plan.files and plan.about != "A" and state.get("b"))


def fresh_task(state: State) -> FreshTask:
    return {"question": state["question"], "b": state["b"]}


def make_fresh_node(
    check: FreshCheck,
) -> Callable[[FreshTask], dict[str, list[Difference]]]:
    def fresh_node(task: FreshTask) -> dict[str, list[Difference]]:
        # A safety net, like the other finders: when it fails, the answer goes on
        # from the parts the search found.
        try:
            found = check(task["question"], task["b"])
        except DifferencesError as exc:
            logger.warning("no new check, the answer goes on: %s", exc)
            found = ()
        return {"differences": list(found)}

    return fresh_node
