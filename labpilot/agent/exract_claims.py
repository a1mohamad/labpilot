import logging
from collections.abc import Callable

from labpilot.agent.claim import Claim
from labpilot.agent.errors import ClaimsError
from labpilot.agent.state import State

logger = logging.getLogger(__name__)

STEP = "extract_claims"


def wants_claim(state: State) -> bool:
    return STEP in state["plan"].steps


def make_claims_node(
    extract: Callable[[str, str], tuple[Claim, ...]],
) -> Callable[[State], dict[str, tuple[Claim, ...]]]:
    def claims_node(state: State) -> dict[str, tuple[Claim, ...]]:
        try:
            claims = extract(state["question"], state["a"])
        except ClaimsError as exc:
            logger.warning("no claims, the answer goes on without them: %s", exc)
            claims = ()
        return {"claims": claims}

    return claims_node
