import logging
from collections.abc import Callable

from labpilot.agent.correspondence import Correspondence
from labpilot.agent.errors import GateError
from labpilot.agent.state import State

logger = logging.getLogger(__name__)


def make_gate_node(
    gate: Callable[[str, str, str, str], Correspondence],
) -> Callable[[State], dict[str, Correspondence | None]]:
    def gate_node(state: State) -> dict[str, Correspondence | None]:
        summary_a = state.get("summary_a", "").strip()
        summary_b = state.get("summary_b", "").strip()
        # With fewer than two files, or when a summary could not be made, there
        # is nothing to compare. The key is still written: an old verdict in the
        # saved chat must never decide this message.
        if not summary_a or not summary_b:
            return {"correspondence": None}
        try:
            found = gate(state["a"], state["b"], summary_a, summary_b)
            return {"correspondence": found}
        except GateError as exc:
            # The gate is a guard and not the evidence, so a gate that cannot
            # judge lets the run go on.
            logger.warning("no verdict, the run goes on: %s", exc)
            return {"correspondence": None}

    return gate_node
