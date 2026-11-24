from collections.abc import Callable
from functools import partial
from typing import TypedDict

from labpilot.agent._safety_net import or_nothing
from labpilot.agent.difference import Difference
from labpilot.agent.errors import DifferencesError
from labpilot.agent.state import State

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
        run = partial(check, task["question"], task["b"])
        return {"differences": or_nothing(run, DifferencesError, "new check")}

    return fresh_node
