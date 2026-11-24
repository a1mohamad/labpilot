import logging
from collections.abc import Sequence

from labpilot.agent._quote import has_quote
from labpilot.agent._schema import index, is_located, list_schema
from labpilot.agent.claim import CLAIM_KINDS, METHOD, RESULT, Claim
from labpilot.agent.errors import ClaimsError

logger = logging.getLogger(__name__)

CLAIMS_TOOL_NAME = "list_claims"

# One group of about 2,000 tokens gave up to about 40 claims when it was measured.
# More than this from ONE group is a runaway, not a careful list.
MAX_CLAIMS_PER_ANSWER = 80


def claims_schema() -> dict[str, object]:
    return list_schema(
        "claims",
        {
            "text": {"type": "string"},
            "part": {"type": "integer"},
            "quote": {"type": "string"},
            "kind": {"type": "string", "enum": list(CLAIM_KINDS)},
        },
        ["text", "part", "quote"],
    )


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
        if not is_located(item):
            raise ClaimsError(
                "every claim needs a 'text', a 'part' (a number) and a 'quote'"
            )

        text = item["text"].strip()
        if not text:
            raise ClaimsError("a claim is blank")
        part = item["part"]
        if index(part, len(sources)) is None:
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
    """The claims of every group, taken in turn, without repeats.

    Round-robin: the first claim of each group, then the second of each, and so
    on. A claim whose text repeats an earlier one (ignoring case and spaces) is
    dropped. Nothing else is: the list is kept whole (D85, D140), and the limit
    that fits a big A belongs to the step that checks the claims.
    """
    joined: list[Claim] = []
    seen: set[str] = set()
    for rank in range(max(map(len, answers), default=0)):
        for answer in answers:
            if rank >= len(answer):
                continue
            claim = answer[rank]
            key = " ".join(claim.text.split()).casefold()
            if key in seen:
                continue
            seen.add(key)
            joined.append(claim)
    return tuple(joined)
