import logging
from collections.abc import Callable
from typing import TypedDict

from labpilot.agent.bug import Bug
from labpilot.agent.errors import BugsError
from labpilot.agent.state import State

logger = logging.getLogger(__name__)

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
        # A safety net, like the scan: when it fails, the answer goes on.
        try:
            found = find(task["artifact"], task["summary"])
        except BugsError as exc:
            logger.warning("no bugs, the answer goes on: %s", exc)
            found = ()
        return {"bugs": list(found)}

    return find_bugs_node
