import logging
from collections.abc import Sequence

from labpilot.agent._quote import has_quote
from labpilot.agent.claim import CLAIM_KINDS, METHOD, RESULT, Claim
from labpilot.agent.errors import ClaimsError

logger = logging.getLogger(__name__)

CLAIMS_TOOL_NAME = "list_claims"

# One group of about 2,000 tokens gave up to about 40 claims when it was measured.
# More than this from ONE group is a runaway, not a careful list.
MAX_CLAIMS_PER_ANSWER = 80

# How many method claims are checked, after the groups are joined. Every one is
# a search and a check, and an "absent" one up to two more of each, so this is a
# cost limit: about 70 short calls for a question. Measured: two groups of the
# sample paper gave about 45 method claims, so nothing was cut there.
MAX_CLAIMS = 48


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
                        "kind": {"type": "string", "enum": list(CLAIM_KINDS)},
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
    if len(items) > MAX_CLAIMS_PER_ANSWER:
        raise ClaimsError(f"{len(items)} claims, the limit is {MAX_CLAIMS_PER_ANSWER}")

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
        # A kind the model left out or spelled its own way is a method claim:
        # checking a result costs a little, never checking a method loses a fact.
        kind = RESULT if item.get("kind") == RESULT else METHOD

        # A claim whose quote is not in its part was made up, so it is dropped.
        if has_quote(texts[part], item["quote"]):
            claims.append(Claim(text, sources[part], item["quote"].strip(), kind))

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


def join_claims(answers: Sequence[Sequence[Claim]]) -> tuple[Claim, ...]:
    """The claims of every group, taken in turn, without repeats, capped.

    Round-robin: the first claim of each group, then the second of each, and so
    on, so no group is starved and none fills the list alone. A claim whose
    text repeats an earlier one (ignoring case and spaces) is dropped. Only
    method claims count toward MAX_CLAIMS, because only they are checked.
    """
    joined: list[Claim] = []
    seen: set[str] = set()
    methods = 0
    for rank in range(max(map(len, answers), default=0)):
        for answer in answers:
            if rank >= len(answer):
                continue
            claim = answer[rank]
            key = " ".join(claim.text.split()).casefold()
            if key in seen:
                continue
            if claim.kind == METHOD:
                if methods >= MAX_CLAIMS:
                    continue
                methods += 1
            seen.add(key)
            joined.append(claim)
    return tuple(joined)
