from collections.abc import Callable
from typing import Any

from labpilot.agent.state import Chunks, State, Totals


def make_respond_node(
    make_prompt: Callable[[Chunks, str, Totals, dict[str, str]], tuple[str, Chunks]],
    generate: Callable[[str], Any],
) -> Callable[[State], dict[str, Any]]:
    def respond_node(state: State) -> dict[str, Any]:
        summaries = {"A": state.get("summary_a", ""), "B": state.get("summary_b", "")}
        prompt, selected = make_prompt(
            state["chunks"], state["question"], state["totals"], summaries
        )
        return {"prompt": prompt, "selected": selected, "result": generate(prompt)}

    return respond_node
