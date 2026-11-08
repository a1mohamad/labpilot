import re
from collections.abc import Sequence

from labpilot.agent._quote import place_quote
from labpilot.agent.bug import Bug
from labpilot.agent.errors import BugsError
from labpilot.ingest import Chunk

CHECKLIST_TOOL_NAME = "list_obligations"
CHECKLIST_AUDIT_TOOL_NAME = "answer_checklist"

# One checklist question asks for at most 20. More than this is a runaway.
MAX_OBLIGATIONS = 40
# The answers of the checklist audit.
MEETS = ("yes", "no", "n/a")


def checklist_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "obligations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["obligations"],
    }


def read_checklist(arguments: dict[str, object]) -> tuple[str, ...]:
    items = arguments.get("obligations")
    if not isinstance(items, list):
        raise BugsError(f"'obligations' must be a list, got {type(items).__name__}")
    if len(items) > MAX_OBLIGATIONS:
        raise BugsError(f"{len(items)} obligations, the limit is {MAX_OBLIGATIONS}")
    rules = tuple(
        item.strip() for item in items if isinstance(item, str) and item.strip()
    )
    if not rules:
        raise BugsError("the checklist has no obligation")
    return rules


def merge_obligations(lists: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """Each obligation once, in order: the same words are the same obligation."""
    kept: dict[str, str] = {}
    for rules in lists:
        for rule in rules:
            kept.setdefault(" ".join(re.findall(r"[a-z0-9]+", rule.lower())), rule)
    return tuple(kept.values())


def checklist_audit_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer"},
                        "meets": {"type": "string", "enum": list(MEETS)},
                        "part": {"type": "integer"},
                        "quote": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["n", "meets"],
                },
            },
        },
        "required": ["answers"],
    }


def _index(value: object, below: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value < below else None


def read_checklist_audit(
    arguments: dict[str, object],
    obligations: Sequence[str],
    sources: Sequence[str],
    texts: Sequence[str],
    chunks: Sequence[Chunk] | None = None,
) -> tuple[Bug, ...]:
    """Each obligation the work breaks, as a concept suspect.

    A "no" with no valid part, or with a quote that is in no part, is dropped:
    it cannot be placed. The answer is refused only when it answers nothing.
    """
    if len(sources) != len(texts):
        raise ValueError("every part needs a source and a text")

    items = arguments.get("answers")
    if not isinstance(items, list):
        raise BugsError(f"'answers' must be a list, got {type(items).__name__}")

    answered = 0
    found: list[Bug] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        number = _index(item.get("n"), len(obligations))
        if number is None or item.get("meets") not in MEETS:
            continue
        answered += 1
        part, quote = _index(item.get("part"), len(texts)), item.get("quote")
        if item["meets"] != "no" or part is None or not isinstance(quote, str):
            continue
        placed = place_quote(part, quote, texts)
        if placed is None:
            continue
        at, quote = placed
        text = item.get("text")
        said = text.strip() if isinstance(text, str) else ""
        found.append(
            Bug(
                "concept",
                f"{said or 'It breaks this rule.'} [obligation: {obligations[number]}]",
                sources[at],
                quote,
                evidence=chunks[at] if chunks is not None else None,
            )
        )
    if not answered:
        raise BugsError("the audit answers no obligation of the checklist")
    return tuple(found)
