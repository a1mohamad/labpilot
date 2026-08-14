from __future__ import annotations

import re

from labpilot.ingest.contracts import Piece

HEADER = re.compile(r"^(#{1,6})\s+(\S.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")


def split_markdown(text: str) -> list[Piece]:
    lines = text.splitlines()
    headers = _header_lines(lines)
    return _pieces(lines, _sections(lines, headers))


def _header_lines(lines: list[str]) -> list[tuple[int, str]]:
    headers = []
    in_fence = False
    for index, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADER.match(line)
        if match:
            headers.append((index, match.group(2).strip()))
    return headers


def _sections(
    lines: list[str], headers: list[tuple[int, str]]
) -> list[tuple[int, int, str]]:
    if not headers:
        return [(0, len(lines), "")]
    sections = []
    if headers[0][0] > 0:
        sections.append((0, headers[0][0], ""))
    for position, (index, title) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        sections.append((index, end, title))
    return sections


def _pieces(lines: list[str], sections: list[tuple[int, int, str]]) -> list[Piece]:
    pieces = []
    for start, end, label in sections:
        while start < end and not lines[start].strip():
            start += 1
        while end > start and not lines[end - 1].strip():
            end -= 1
        if start >= end:
            continue
        pieces.append(
            Piece(
                text="\n".join(lines[start:end]),
                start_line=start + 1,
                end_line=end,
                label=label,
            )
        )
    return pieces
