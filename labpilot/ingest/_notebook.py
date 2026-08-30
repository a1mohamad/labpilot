from __future__ import annotations

import json
import re
from typing import Any

from labpilot.ingest._plain import load_text
from labpilot.ingest._sections import Mark, to_pieces
from labpilot.ingest.contracts import Piece
from labpilot.ingest.errors import LoaderError

CELL_MARK = re.compile(r"^# %% cell (\d+) \[(\w+)\]")
OUTPUT_SEPARTOR = "# --- output ---"
TEXT_MIME = "text/plain"


def load_notebook(raw: bytes) -> str:
    blocks = []
    for number, cell in enumerate(_cells(raw), start=1):
        block = _cell_text(cell, number=number)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def _cells(raw: str) -> list[Any]:
    try:
        notebook = json.loads(load_text(raw))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"not valid as JSON, so not a notebook: {exc}") from exc

    if not isinstance(notebook, dict):
        raise LoaderError("a notebook must be a JSON object")

    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise LoaderError(
            "no 'cells' list: nbformat 3 and earlier used 'worksheets' "
            "are not supported"
        )

    return cells


def _cell_text(cell: Any, *, number: int) -> str:
    if not isinstance(cell, dict):
        return ""

    source = _join(cell.get("source"))
    if cell.get("cell_type") == "code":
        body = _with_outputs(source, cell.get("outputs"))
    else:
        body = source

    if not body.strip():
        return ""

    return f"{_mark(cell, number)}\n{body}"


def _mark(cell: dict[str, Any], number: int) -> str:
    kind = cell.get("cell_type", "unknown")
    if kind != "code":
        return f"# %% cell {number} [{kind}]"
    count = cell.get("execution_count")
    return f"# %% cell {number} [code] {_ran(count)}"


def _ran(count: Any) -> str:
    return f"run {count}" if isinstance(count, int) else "not run"


def _with_outputs(source: str, outputs: Any) -> str:
    texts = [text for text in map(_output_text, _listed(outputs)) if text.strip()]
    if not texts:
        return source

    parts = [source] if source.strip() else []
    parts.append(OUTPUT_SEPARTOR)
    parts.extend(texts)
    return "\n".join(parts)


def _output_text(output: Any) -> str:
    if not isinstance(output, dict):
        return ""

    kind = output.get("output_type")
    if kind == "stream":
        return _join(output.get("text"))
    if kind in ("execute_result", "display_data"):
        data = output.get("data")
        # text/plain only. An image output has no text/plain and is dropped,
        # which is the point: base64 PNG is noise and can be megabytes.
        return _join(data.get(TEXT_MIME)) if isinstance(data, dict) else ""
    if kind == "error":
        named = (str(output.get("ename", "")), str(output.get("evalue", "")))
        return ": ".join(part for part in named if part)

    return ""


def _listed(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _join(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # nbformat keeps every line's own trailing newline, so join with "".
        return "".join(part for part in value if isinstance(part, str))
    return ""


def split_notebook(text: str) -> list[Piece]:
    lines = text.splitlines()
    return to_pieces(lines, _mark_lines(lines))


def _mark_lines(lines: list[str]) -> list[Mark]:
    marks = []
    for index, line in enumerate(lines):
        match = CELL_MARK.match(line)
        if match:
            marks.append((index, f"cell {match.group(1)} {match.group(2)}"))

    return marks
