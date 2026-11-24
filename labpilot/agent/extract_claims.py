from collections.abc import Callable
from functools import partial

from labpilot.agent._safety_net import or_nothing
from labpilot.agent.claim import Claim
from labpilot.agent.errors import ClaimsError
from labpilot.agent.state import State


def make_claims_node(
    extract: Callable[[str], tuple[Claim, ...]],
) -> Callable[[State], dict[str, tuple[Claim, ...]]]:
    def claims_node(state: State) -> dict[str, tuple[Claim, ...]]:
        found = or_nothing(partial(extract, state["a"]), ClaimsError, "claims")
        return {"claims": tuple(found)}

    return claims_node
