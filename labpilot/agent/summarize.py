from collections.abc import Callable
from typing import Literal

from labpilot.agent.state import State

Source = Literal["a", "b"]


def make_summarize_node(
    source: Source, summarize: Callable[[str], str]
) -> Callable[[State], dict[str, str]]:
    def summarize_node(state: State) -> dict[str, str]:
        return {f"summary_{source}": summarize(state[source])}

    return summarize_node
