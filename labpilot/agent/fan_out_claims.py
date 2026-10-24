from langgraph.types import Send

from labpilot.agent.check_one import EVIDENCE_SIDE
from labpilot.agent.state import State


def fan_out_claims(state: State) -> str | list[Send]:
    claims = state.get("claims", ())
    if not claims:
        return "respond"

    sides = {EVIDENCE_SIDE: state["sides"][EVIDENCE_SIDE]}
    return [Send("check_one", {"sides": sides, "claim": claim}) for claim in claims]
