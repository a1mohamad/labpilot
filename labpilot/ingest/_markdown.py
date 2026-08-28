from __future__ import annotations

import re

from labpilot.ingest._sections import Mark, to_pieces
from labpilot.ingest.contracts import Piece

HEADER = re.compile(r"^(#{1,6})\s+(\S.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")


def split_markdown(text: str) -> list[Piece]:
    lines = text.splitlines()
    return to_pieces(lines, _header_lines(lines))


def _header_lines(lines: list[str]) -> list[Mark]:
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
