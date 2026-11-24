from collections.abc import Callable
from functools import partial
from typing import TypedDict

from labpilot.agent._safety_net import or_nothing
from labpilot.agent.bug import Bug
from labpilot.agent.errors import BugsError
from labpilot.agent.state import State

STEP = "find_bugs"

FindBugs = Callable[[str, str], tuple[Bug, ...]]


class BugsTask(TypedDict):
    artifact: str
    summary: str


def wants_bugs(state: State) -> bool:
    return STEP in state["plan"].steps


def bugs_task(state: State) -> BugsTask | None:
    # Only B is hunted, the work being checked (D106). A is the reference the
    # person chose to trust: hunting it would go against that choice, and could
    # make them doubt a good reference over bugs that are not there. A file in
    # slot A alone is explained, not hunted (the REFERENCE instruction).
    if state.get("b"):
        return {"artifact": state["b"], "summary": state.get("summary_b", "")}
    return None


def make_find_bugs_node(find: FindBugs) -> Callable[[BugsTask], dict[str, list[Bug]]]:
    def find_bugs_node(task: BugsTask) -> dict[str, list[Bug]]:
        hunt = partial(find, task["artifact"], task["summary"])
        return {"bugs": or_nothing(hunt, BugsError, "bugs")}

    return find_bugs_node
