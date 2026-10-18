from collections.abc import Callable

from labpilot.agent.plan import Plan
from labpilot.agent.state import State


def make_planner_node(
    plan: Callable[[str, str, str], Plan],
) -> Callable[[State], dict[str, Plan]]:
    def planner_node(state: State) -> dict[str, Plan]:
        return {"plan": plan(state["question"], state["a"], state["b"])}

    return planner_node
