import logging
import re
from collections.abc import Sequence

from labpilot.agent._quote import place_quote
from labpilot.agent.bug import BUG_KINDS, SEVERITIES, Bug
from labpilot.agent.errors import BugsError
from labpilot.ingest import Chunk

logger = logging.getLogger(__name__)

BUGS_TOOL_NAME = "list_defects"

# One group gave up to about 30 suspects when it was measured. More than this
# from ONE call is a runaway.
MAX_BUGS_PER_ANSWER = 40


def bugs_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "defects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(BUG_KINDS)},
                        "part": {"type": "integer"},
                        "quote": {"type": "string"},
                        "text": {"type": "string"},
                        "severity": {"type": "string", "enum": list(SEVERITIES)},
                    },
                    "required": ["kind", "part", "quote", "text"],
                },
            },
        },
        "required": ["defects"],
    }


def _complete(item: object, parts: int) -> bool:
    # A bool is an int in Python; a model that writes true is not naming a part.
    return (
        isinstance(item, dict)
        and isinstance(item.get("text"), str)
        and bool(item["text"].strip())
        and isinstance(item.get("part"), int)
        and not isinstance(item.get("part"), bool)
        and 0 <= item["part"] < parts
        and isinstance(item.get("quote"), str)
    )


def read_bugs(
    arguments: dict[str, object],
    sources: Sequence[str],
    texts: Sequence[str],
    chunks: Sequence[Chunk] | None = None,
) -> tuple[Bug, ...]:
    if len(sources) != len(texts):
        raise ValueError("every part needs a source and a text")

    items = arguments.get("defects")
    if not isinstance(items, list):
        raise BugsError(f"'defects' must be a list, got {type(items).__name__}")
    if len(items) > MAX_BUGS_PER_ANSWER:
        raise BugsError(f"{len(items)} defects, the limit is {MAX_BUGS_PER_ANSWER}")

    # One bad suspect is dropped, not the whole answer (2026-11-02: one item
    # that missed a field made three tiers refuse a whole group).
    found: list[Bug] = []
    for item in items:
        if not _complete(item, len(sources)):
            continue
        # A suspect whose quote is in no part was made up: dropped.
        placed = place_quote(item["part"], item["quote"], texts)
        if placed is None:
            continue
        at, quote = placed
        kind = item["kind"] if item.get("kind") in BUG_KINDS else "code"
        severity = item["severity"] if item.get("severity") in SEVERITIES else "high"
        evidence = chunks[at] if chunks is not None else None
        found.append(
            Bug(
                kind,
                item["text"].strip(),
                sources[at],
                quote,
                severity,
                evidence=evidence,
            )
        )

    dropped = len(items) - len(found)
    if dropped:
        logger.warning(
            "%d of %d suspects dropped: a field is missing or the quote is in no part",
            dropped,
            len(items),
        )
    if items and not found:
        raise BugsError("no suspect is complete with a quote that is in a part")
    return tuple(found)


def merge_bugs(found: Sequence[Bug]) -> tuple[Bug, ...]:
    """Each suspect once: the first of those on the same line of the same part.

    The questions read the same code apart (the trace of a piece, the method and
    the concept of the whole file), so two of them can point at one line.
    """
    kept: dict[tuple[str, str], Bug] = {}
    for bug in found:
        words = " ".join(re.findall(r"[a-z0-9]+", bug.quote.lower()))
        kept.setdefault((bug.source, words), bug)
    return tuple(kept.values())
