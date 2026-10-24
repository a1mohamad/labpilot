from collections.abc import Callable
from typing import Any

from langgraph.types import Overwrite

from labpilot.agent.state import State


def make_remember_node(
    answer_text: Callable[[Any], str] | None,
) -> Callable[[State], dict[str, Any]]:
    def remember_node(state: State) -> dict[str, Any]:
        remembered: dict[str, Any] = {"history": [state["question"]]}
        if answer_text is not None:
            remembered["last_answer"] = answer_text(state["result"])
        # The answer has read them. The next message starts with none, and this
        # is the one place that says so, as `merge` does for `found`.
        if state.get("claims"):
            remembered["claims"] = ()
        if state.get("findings"):
            remembered["findings"] = Overwrite([])
        if state.get("code_findings"):
            remembered["code_findings"] = Overwrite([])
        return remembered

    return remember_node
