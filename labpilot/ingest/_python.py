from __future__ import annotations

import ast

from labpilot.ingest._recursive import split_recursive
from labpilot.ingest.contracts import Piece
from labpilot.ingest.defaults import MAX_CHARS

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def split_python(text: str) -> list[Piece]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return split_recursive(text)
    lines = text.splitlines()
    return _split_body(lines, tree.body, 1, len(lines), "")


def _split_body(
    lines: list[str], body: list[ast.stmt], start: int, end: int, prefix: str
) -> list[Piece]:
    pieces: list[Piece] = []
    cursor = start
    for node in body:
        if not isinstance(node, DEFINITIONS):
            continue
        node_start, node_end = _span(node)
        if node_start > cursor:
            pieces.extend(_piece(lines, cursor, node_start - 1, prefix))
        pieces.extend(_split_definition(lines, node, node_start, node_end, prefix))
        cursor = node_end + 1
    if cursor <= end:
        pieces.extend(_piece(lines, cursor, end, prefix))
    return pieces


def _split_definition(
    lines: list[str], node: ast.stmt, start: int, end: int, prefix: str
) -> list[Piece]:
    label = _label(node, prefix)
    nested = any(isinstance(child, DEFINITIONS) for child in node.body)
    if not nested or len(_join(lines, start, end)) <= MAX_CHARS:
        return _piece(lines, start, end, label)
    return _split_body(lines, node.body, start, end, label)


def _span(node: ast.stmt) -> tuple[int, int]:
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return start, node.end_lineno


def _label(node: ast.stmt, prefix: str) -> str:
    kind = "class" if isinstance(node, ast.ClassDef) else "def"
    name = f"{kind} {node.name}"
    return f"{prefix} · {name}" if prefix else name


def _join(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _piece(lines: list[str], start: int, end: int, label: str) -> list[Piece]:
    while start <= end and not lines[start - 1].strip():
        start += 1
    while end >= start and not lines[end - 1].strip():
        end -= 1
    if start > end:
        return []
    return [
        Piece(
            text=_join(lines, start, end),
            start_line=start,
            end_line=end,
            label=label,
        )
    ]
