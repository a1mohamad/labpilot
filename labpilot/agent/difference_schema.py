from collections.abc import Sequence

from labpilot.agent._quote import has_quote
from labpilot.agent.difference import (
    AUDIT,
    DIFFERS,
    MISSING,
    SCAN,
    SILENT,
    Difference,
)
from labpilot.agent.errors import DifferencesError

AUDIT_TOOL_NAME = "give_verdicts"
SCAN_TOOL_NAME = "list_items"
JUDGE_TOOL_NAME = "judge_findings"
MERGE_TOOL_NAME = "group_findings"

SAME = "same"
NOT_APPLICABLE = "n/a"
AUDIT_VERDICTS = (SAME, DIFFERS, MISSING, NOT_APPLICABLE)

REAL = "real"
MINOR = "minor"
FALSE = "false"
JUDGE_VERDICTS = (REAL, MINOR, FALSE)
RELATIONS = ("silent", "differs", "same", "none")


def _answers(properties: dict, required: list[str], key: str) -> dict:
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        },
        "required": [key],
    }


def audit_schema() -> dict[str, object]:
    return _answers(
        {
            "n": {"type": "integer"},
            "verdict": {"type": "string", "enum": list(AUDIT_VERDICTS)},
            "part": {"type": "integer"},
            "quote": {"type": "string"},
            "why": {"type": "string"},
        },
        ["n", "verdict"],
        "answers",
    )


def scan_schema() -> dict[str, object]:
    return _answers(
        {
            "part": {"type": "integer"},
            "quote": {"type": "string"},
            "what": {"type": "string"},
            "why": {"type": "string"},
        },
        ["part", "quote", "what"],
        "items",
    )


def judge_schema() -> dict[str, object]:
    return _answers(
        {
            "n": {"type": "integer"},
            "verdict": {"type": "string", "enum": list(JUDGE_VERDICTS)},
            "relation": {"type": "string", "enum": list(RELATIONS)},
            "why": {"type": "string"},
        },
        ["n", "verdict", "relation"],
        "answers",
    )


def merge_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "integer"}},
            }
        },
        "required": ["groups"],
    }


def _number(value: object) -> int | None:
    # bool is an int in Python; a model that writes true is not naming a part.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _placed(
    part: object, quote: str, sources: Sequence[str], texts: Sequence[str]
) -> tuple[str, str] | None:
    """(source, quote) of the part the quote is really in, or None if it is in none.

    The named part first, then any part: a model often names the wrong number.
    """
    if not quote.strip():
        return None
    named = _number(part)
    order = [named] if named is not None and 0 <= named < len(texts) else []
    order += [i for i in range(len(texts)) if i != named]
    for i in order:
        if has_quote(texts[i], quote):
            return sources[i], quote
    return None


def read_audit(
    arguments: dict,
    facts: Sequence[str],
    numbers: Sequence[int],
    sources: Sequence[str],
    texts: Sequence[str],
) -> dict[int, tuple[str, Difference | None]]:
    """fact number -> (verdict, the Difference for "differs" and "missing").

    `numbers` are the fact numbers this call was asked about; an answer for any
    other number is ignored. A "differs" or "missing" whose quote is in none of
    the parts keeps its verdict with an empty quote: the judge reads the code.
    """
    answers = arguments.get("answers")
    if not isinstance(answers, list):
        raise DifferencesError("the audit gave no list of answers")

    asked = set(numbers)
    out: dict[int, tuple[str, Difference | None]] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        n = _number(answer.get("n"))
        verdict = answer.get("verdict")
        if n is None or n not in asked or verdict not in AUDIT_VERDICTS:
            continue
        if verdict in (DIFFERS, MISSING):
            quote = str(answer.get("quote") or "")
            placed = _placed(answer.get("part"), quote, sources, texts)
            source, quote = placed if placed else ("", "")
            difference = Difference(
                kind=verdict,
                text=str(answer.get("why") or "").strip(),
                source=source,
                quote=quote,
                fact=facts[n],
                found_by=AUDIT,
            )
            out[n] = (verdict, difference)
        else:
            out[n] = (verdict, None)

    if not out:
        raise DifferencesError("the audit answered none of the facts it was asked")
    return out


def read_scan(
    arguments: dict, sources: Sequence[str], texts: Sequence[str]
) -> tuple[Difference, ...]:
    """The scan's items. An item whose quote is in none of the parts is dropped."""
    items = arguments.get("items")
    if not isinstance(items, list):
        raise DifferencesError("the scan gave no list of items")

    found: list[Difference] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        what = str(item.get("what") or "").strip()
        placed = _placed(item.get("part"), str(item.get("quote") or ""), sources, texts)
        if not what or placed is None:
            continue
        why = str(item.get("why") or "").strip()
        found.append(
            Difference(
                kind=SILENT,
                text=f"{what} {why}".strip(),
                source=placed[0],
                quote=placed[1],
                found_by=SCAN,
            )
        )
    return tuple(found)


def read_judge(arguments: dict, count: int) -> dict[int, tuple[str, str, str]]:
    """finding number -> (verdict, relation, reason)."""
    answers = arguments.get("answers")
    if not isinstance(answers, list):
        raise DifferencesError("the judge gave no list of answers")

    out: dict[int, tuple[str, str, str]] = {}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        n = _number(answer.get("n"))
        verdict = answer.get("verdict")
        relation = answer.get("relation")
        if n is None or not 0 <= n < count or verdict not in JUDGE_VERDICTS:
            continue
        if relation not in RELATIONS:
            relation = "none"
        out[n] = (verdict, relation, str(answer.get("why") or "").strip())

    if not out:
        raise DifferencesError("the judge answered none of the findings")
    return out


def read_merge(arguments: dict, allowed: Sequence[int]) -> list[list[int]]:
    """Groups of findings that make the same point; each finding in one group only."""
    groups = arguments.get("groups")
    if not isinstance(groups, list):
        raise DifferencesError("the merge gave no list of groups")

    ok = set(allowed)
    taken: set[int] = set()
    out: list[list[int]] = []
    for group in groups:
        if not isinstance(group, list):
            continue
        members = sorted(
            {n for n in (_number(x) for x in group) if n in ok and n not in taken}
        )
        if len(members) >= 2:
            out.append(members)
            taken.update(members)
    return out
