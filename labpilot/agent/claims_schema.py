from collections.abc import Sequence

from labpilot.agent.claim import Claim
from labpilot.agent.errors import ClaimsError

CLAIMS_TOOL_NAME = "list_claims"

MAX_CLAIMS = 20


def claims_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "part": {"type": "integer"},
                    },
                    "required": ["text", "part"],
                },
            },
        },
        "required": ["claims"],
    }


def read_claims(
    arguments: dict[str, object], sources: Sequence[str]
) -> tuple[Claim, ...]:
    items = arguments.get("claims")
    if not isinstance(items, list):
        raise ClaimsError(f"'claims' must be  a list, got {type(items).__name__}")
    if len(items) > MAX_CLAIMS:
        raise ClaimsError(f"{len(items)} claims, the limit is {MAX_CLAIMS}")

    claims: list[Claim] = []
    for item in items:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and isinstance(item.get("part"), int)
            and not isinstance(item.get("part"), bool)
        ):
            raise ClaimsError("every claim needs a 'text'(text) and a 'part'(a number)")

        text = item.get("text").strip()
        if not text:
            raise ClaimsError("a claim is blank")
        part = item.get("part")
        if not 0 <= part < len(sources):
            raise ClaimsError(
                f"a claim names part {part}, but the parts are 0 to {len(sources) - 1}"
            )
        claims.append(Claim(text, sources[part]))

    return tuple(claims)
