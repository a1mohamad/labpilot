import logging
from collections.abc import Sequence

from labpilot.agent._quote import has_quote
from labpilot.agent.code_finding import A_SILENT, CodeFinding
from labpilot.agent.errors import DifferencesError
from labpilot.ingest import Chunk

logger = logging.getLogger(__name__)

DIFFERENCES_TOOL_NAME = "list_differences"

# One group of about 2,000 tokens of B gave up to about 10 items when it was
# measured. More than this from ONE group is a runaway.
MAX_ITEMS_PER_ANSWER = 40


def differences_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "part": {"type": "integer"},
                        "quote": {"type": "string"},
                        "a_says": {"type": "string"},
                    },
                    "required": ["text", "part", "quote", "a_says"],
                },
            },
        },
        "required": ["items"],
    }


def read_code_findings(
    arguments: dict[str, object],
    sources: Sequence[str],
    texts: Sequence[str],
    chunks: Sequence[Chunk] | None = None,
) -> tuple[CodeFinding, ...]:
    if len(sources) != len(texts):
        raise ValueError("every part needs a source and a text")

    items = arguments.get("items")
    if not isinstance(items, list):
        raise DifferencesError(f"'items' must be a list, got {type(items).__name__}")
    if len(items) > MAX_ITEMS_PER_ANSWER:
        raise DifferencesError(
            f"{len(items)} items, the limit is {MAX_ITEMS_PER_ANSWER}"
        )

    found: list[CodeFinding] = []
    for item in items:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and isinstance(item.get("part"), int)
            and not isinstance(item.get("part"), bool)
            and isinstance(item.get("quote"), str)
        ):
            raise DifferencesError(
                "every item needs a 'text', a 'part'(a number) and a 'quote'"
            )
        text = item["text"].strip()
        part = item["part"]
        if not text:
            raise DifferencesError("an item is blank")
        if not 0 <= part < len(sources):
            raise DifferencesError(
                f"an item names part {part}, but the parts are 0 to {len(sources) - 1}"
            )
        a_says = item.get("a_says")
        a_says = (
            a_says.strip() if isinstance(a_says, str) and a_says.strip() else A_SILENT
        )

        # An item whose quote is not in its part of B was made up: dropped.
        if has_quote(texts[part], item["quote"]):
            evidence = chunks[part] if chunks is not None else None
            found.append(
                CodeFinding(
                    text, sources[part], item["quote"].strip(), a_says, evidence
                )
            )

    dropped = len(items) - len(found)
    if dropped:
        logger.warning(
            "%d of %d code findings dropped: their quote is not in their part",
            dropped,
            len(items),
        )
    if items and not found:
        raise DifferencesError("no item has a quote that is in its part")
    return tuple(found)
