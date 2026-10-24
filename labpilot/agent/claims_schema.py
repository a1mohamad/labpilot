import logging
from collections.abc import Sequence

from labpilot.agent._quote import has_quote
from labpilot.agent.claim import Claim
from labpilot.agent.errors import ClaimsError

logger = logging.getLogger(__name__)

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
                        "quote": {"type": "string"},
                    },
                    "required": ["text", "part", "quote"],
                },
            },
        },
        "required": ["claims"],
    }


def read_claims(
    arguments: dict[str, object], sources: Sequence[str], texts: Sequence[str]
) -> tuple[Claim, ...]:
    if len(sources) != len(texts):
        raise ValueError("every part needs a source and a text")

    items = arguments.get("claims")
    if not isinstance(items, list):
        raise ClaimsError(f"'claims' must be a list, got {type(items).__name__}")
    if len(items) > MAX_CLAIMS:
        raise ClaimsError(f"{len(items)} claims, the limit is {MAX_CLAIMS}")

    claims: list[Claim] = []
    for item in items:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and isinstance(item.get("part"), int)
            and not isinstance(item.get("part"), bool)
            and isinstance(item.get("quote"), str)
        ):
            raise ClaimsError(
                "every claim needs a 'text', a 'part'(a number) and a 'quote'"
            )

        text = item["text"].strip()
        if not text:
            raise ClaimsError("a claim is blank")
        part = item["part"]
        if not 0 <= part < len(sources):
            raise ClaimsError(
                f"a claim names part {part}, but the parts are 0 to {len(sources) - 1}"
            )

        # A claim whose quote is not in its part was made up, so it is dropped.
        if has_quote(texts[part], item["quote"]):
            claims.append(Claim(text, sources[part], item["quote"].strip()))

    dropped = len(items) - len(claims)
    if dropped:
        logger.warning(
            "%d of %d claims dropped: their quote is not in their part",
            dropped,
            len(items),
        )
    if items and not claims:
        raise ClaimsError("no claim has a quote that is in its part")

    return tuple(claims)
