from collections.abc import Callable
from typing import Literal

from labpilot.agent.state import State

Slot = Literal["a", "b"]


def make_summarize_node(
    slot: Slot, summarize: Callable[[str], str]
) -> Callable[[State], dict[str, str]]:
    def summarize_node(state: State) -> dict[str, str]:
        return {f"summary_{slot}": summarize(state[slot])}

    return summarize_node
