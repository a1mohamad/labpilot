from collections.abc import Callable
from typing import Literal

from labpilot.agent.state import State

Slot = Literal["a", "b"]


def make_summarize_node(
    slot: Slot, summarize: Callable[[str], str]
) -> Callable[[State], dict[str, str]]:
    def summarize_node(state: State) -> dict[str, str]:
        artifact_id = state[slot]
        if not artifact_id:
            return {}
        return {f"summary_{slot}": summarize(artifact_id)}

    return summarize_node
