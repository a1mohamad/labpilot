from labpilot.agent.correspondence import GATE_VERDICTS, Correspondence
from labpilot.agent.errors import GateError

GATE_TOOL_NAME = "judge_correspondence"

# The reason is shown to the user on a halt, so it is kept short.
MAX_REASON_CHARS = 600


def gate_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(GATE_VERDICTS)},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "reason"],
    }


def read_correspondence(arguments: dict[str, object]) -> Correspondence:
    verdict = arguments.get("verdict")
    # A tier that answers in text may write "none" or " Partial". The meaning is
    # the same, so the case and the spaces are not a reason to refuse it.
    if isinstance(verdict, str):
        verdict = verdict.strip().upper()
    if verdict not in GATE_VERDICTS:
        raise GateError(f"the verdict must be one of {GATE_VERDICTS}, got {verdict!r}")

    reason = arguments.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise GateError("every verdict needs a 'reason'(text)")

    return Correspondence(verdict, " ".join(reason.split())[:MAX_REASON_CHARS])
