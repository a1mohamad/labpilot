from collections.abc import Sequence

from labpilot.agent._quote import has_quote
from labpilot.agent.claim import Claim
from labpilot.agent.errors import CheckError
from labpilot.agent.finding import Finding

CHECK_TOOL_NAME = "give_verdict"

VERDICTS = ("match", "mismatch", "absent")
KINDS = ("choice", "mistake", "unclear")


def check_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": list(VERDICTS)},
            "kind": {"type": "string", "enum": list(KINDS)},
            "part": {"type": "integer"},
            "quote": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["verdict", "note"],
    }


def read_finding(
    arguments: dict[str, object],
    claim: Claim,
    sources: Sequence[str],
    texts: Sequence[str],
) -> Finding:
    if len(sources) != len(texts):
        raise ValueError("every part needs a source and a text")

    verdict = arguments.get("verdict")
    if verdict not in VERDICTS:
        raise CheckError(f"the verdict must be one of {VERDICTS}, got {verdict!r}")
    note = arguments.get("note")
    if not isinstance(note, str):
        raise CheckError("every verdict needs a 'note'(text)")
    note = note.strip()

    # Nothing was found, so there is no part to point at and no quote to check.
    if verdict == "absent":
        return Finding(claim, verdict, "", "", "", note)

    part = arguments.get("part")
    if not isinstance(part, int) or isinstance(part, bool):
        raise CheckError(f"a {verdict} needs a 'part'(a number)")
    if not 0 <= part < len(texts):
        raise CheckError(
            f"the verdict names part {part}, but the parts are 0 to {len(texts) - 1}"
        )
    quote = arguments.get("quote")
    if not isinstance(quote, str) or not has_quote(texts[part], quote):
        raise CheckError(f"the quote is not in part {part}")

    kind = ""
    if verdict == "mismatch":
        kind = arguments.get("kind")
        if kind not in KINDS:
            raise CheckError(f"a mismatch needs a kind from {KINDS}, got {kind!r}")

    return Finding(claim, verdict, kind, sources[part], quote.strip(), note)
