from collections.abc import Callable
from typing import Any

from labpilot.agent.state import Chunks, State, Totals


def make_measure_node(
    measure: Callable[[str, str], Any], fits: Callable[[Any, str, str], bool]
) -> Callable[[State], dict[str, Any]]:
    def measure_node(state: State) -> dict[str, Any]:
        sides = measure(state["a"], state["b"])
        # The last answer is counted too: the answer prompt carries it whole.
        fitted = fits(sides, state["question"], state.get("last_answer", ""))
        return {"sides": sides, "fits": fitted}

    return measure_node


def make_stuff_node(
    stuff: Callable[[Any, str], tuple[Chunks, Totals]],
) -> Callable[[State], dict[str, Any]]:
    def stuff_node(state: State) -> dict[str, Any]:
        chunks, totals = stuff(state["sides"], state["question"])
        return {"chunks": chunks, "totals": totals}

    return stuff_node
