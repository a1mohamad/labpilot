from __future__ import annotations

import json

from labpilot._text import truncate
from labpilot.llm.contracts import Tool
from labpilot.llm.errors import LLMError


def json_fallback(tool: Tool) -> str:
    return (
        f"Answer by calling the function {tool.name}. If you cannot call a "
        "function, answer with only one JSON object that matches this schema, "
        f"and no other text:\n{json.dumps(tool.parameters)}"
    )


def read_object(text: str, source: str) -> dict[str, object]:
    start = text.find("{")
    if start == -1:
        raise LLMError(f"{source}: the answer is hold no JSON object: {truncate(text)}")

    try:
        value, _ = json.JSONDecoder().raw_decode(text, start)
    except ValueError as exc:
        raise LLMError(
            f"{source}: the JSON object is not valid: {truncate(text)}"
        ) from exc

    return value


def read_arguments(raw: object, source: str) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw

    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise LLMError(
                f"{source}: the function arguments are not JSON: {truncate(raw)}"
            ) from exc
        if isinstance(value, dict):
            return value

    raise LLMError(
        f"{source}: the function arguments are not an object: {truncate(str(raw))}"
    )
