from collections.abc import Callable
from typing import Any

from labpilot.agent.state import State


def make_rewrite_node(
    rewrite: Callable[[str, list[str], str], str],
) -> Callable[[State], dict[str, Any]]:
    def rewrite_node(state: State) -> dict[str, Any]:
        history = state.get("history", [])
        if not history:
            return {}

        question = state["question"]
        last_answer = state.get("last_answer", "")
        standalone = " ".join(rewrite(question, list(history), last_answer).split())
        if not standalone or standalone == question:
            return {}

        return {"question": standalone}

    return rewrite_node
