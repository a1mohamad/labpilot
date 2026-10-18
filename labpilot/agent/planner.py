import logging
from collections.abc import Callable

from labpilot.agent.errors import PlanError
from labpilot.agent.plan import Plan
from labpilot.agent.plan_check import check_plan, default_plan, present_sides
from labpilot.agent.state import State

logger = logging.getLogger(__name__)


def make_planner_node(
    plan: Callable[[str, str, str], Plan],
) -> Callable[[State], dict[str, Plan]]:
    def planner_node(state: State) -> dict[str, Plan]:
        question, a, b = state["question"], state["a"], state["b"]
        sides = present_sides(a, b)
        try:
            made = plan(question, a, b)
        except PlanError as exc:
            logger.warning("the planner failed, the default plan runs: %s", exc)
            return {"plan": default_plan(question, sides)}
        return {"plan": check_plan(made, question, sides)}

    return planner_node
