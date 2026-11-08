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


def wants_bug(state: State) -> bool:
    return STEP in state["plan"].steps


def bugs_task(state: State) -> BugsTask | None:
    # One file is read alone: B when there are two (the work being checked),
    # else whichever file there is. Its summary says what the work is for.
    if state.get("b"):
        return {"artifact": state["b"], "summary": state.get("summary_b", "")}
    if state.get("a"):
        return {"artifact": state["a"], "summary": state.get("summary_a", "")}
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
