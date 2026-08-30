from __future__ import annotations

from bisect import bisect_left

from labpilot.ingest.contracts import Piece
from labpilot.ingest.defaults import CHUNK_OVERLAP, CHUNK_SIZE, MAX_CHARS
from labpilot.tokens import CHARS_PER_TOKEN

SEPARATORS: tuple[str, ...] = ("\n\n\n", "\n\n", "\n", " ")

TARGET_CHARS = CHUNK_SIZE * CHARS_PER_TOKEN
OVERLAP_CHARS = CHUNK_OVERLAP * CHARS_PER_TOKEN


def split_recursive(text: str, *, start_line: int = 1) -> list[Piece]:
    if not text.strip():
        return []
    spans = _pack(text, _blocks(text, 0, len(text), 0))
    newlines = _newline_offsets(text)
    pieces = []
    for start, end in spans:
        start, end = _trim(text, start, end)
        if start >= end:
            continue
        pieces.append(
            Piece(
                text=text[start:end],
                start_line=start_line + bisect_left(newlines, start),
                end_line=start_line + bisect_left(newlines, end - 1),
            )
        )
    return pieces


def _blocks(text: str, start: int, end: int, depth: int) -> list[tuple[int, int]]:
    if end - start <= MAX_CHARS:
        return [(start, end)]
    if depth >= len(SEPARATORS):
        return [(i, min(i + MAX_CHARS, end)) for i in range(start, end, MAX_CHARS)]
    parts = _split_on(text, start, end, SEPARATORS[depth])
    if len(parts) == 1:
        return _blocks(text, start, end, depth + 1)
    blocks = []
    for part_start, part_end in parts:
        blocks.extend(_blocks(text, part_start, part_end, depth + 1))
    return blocks


def _split_on(text: str, start: int, end: int, separator: str) -> list[tuple[int, int]]:
    spans = []
    cursor = start
    while (hit := text.find(separator, cursor, end)) != -1:
        stop = hit + len(separator)
        spans.append((cursor, stop))
        cursor = stop
    if cursor < end:
        spans.append((cursor, end))
    return spans or [(start, end)]


def _pack(text: str, blocks: list[tuple[int, int]]) -> list[tuple[int, int]]:
    spans = []
    chunk_start, chunk_end = blocks[0]
    for block_start, block_end in blocks[1:]:
        if block_end - chunk_start <= TARGET_CHARS:
            chunk_end = block_end
            continue
        spans.append((chunk_start, chunk_end))
        floor = max(chunk_start, block_end - MAX_CHARS)
        chunk_start = _snap(text, max(floor, block_start - OVERLAP_CHARS), floor)
        chunk_end = block_end
    spans.append((chunk_start, chunk_end))
    return spans


def _snap(text: str, offset: int, floor: int) -> int:
    # The overlap is a count of characters, so on its own it lands wherever it
    # lands -- measured at 10.8% of chunks beginning inside a word, which both
    # weakens the embedding and makes the first quoted line unusable. Move back
    # to the start of a line, or failing that past a space, never below floor
    # so the chunk still fits MAX_CHARS.
    for separator in ("\n", " "):
        found = text.rfind(separator, floor, offset)
        if found != -1:
            return found + 1
    return offset


def _newline_offsets(text: str) -> list[int]:
    offsets = []
    hit = text.find("\n")
    while hit != -1:
        offsets.append(hit)
        hit = text.find("\n", hit + 1)
    return offsets


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
