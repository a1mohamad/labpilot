from collections.abc import Callable
from typing import Any

from labpilot.agent.correspondence import HALT_VERDICT
from labpilot.agent.state import State


def halted(state: State) -> bool:
    found = state.get("correspondence")
    return found is not None and found.verdict == HALT_VERDICT


def make_halt_node(
    halt_answer: Callable[[str, str, str], Any],
) -> Callable[[State], dict[str, Any]]:
    def halt_node(state: State) -> dict[str, Any]:
        found = state.get("correspondence")
        # `ask()` reads these four keys after every run, and the saved chat would
        # give it the ones of the message before, so all of them are written.
        return {
            "result": halt_answer(state["summary_a"], state["summary_b"], found.reason),
            "chunks": (),
            "selected": (),
            "prompt": "",
            "totals": None,
        }

    return halt_node
