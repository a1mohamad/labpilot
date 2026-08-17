from __future__ import annotations

import re
from dataclasses import dataclass

from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids

_CITATION = re.compile(r'([AB]-\d+)\s+"(.*?)"(?=\s*[,\]])')
_MARKDOWN_ESCAPE = re.compile(r"\\(?=[^\w\s]|_)")


@dataclass(frozen=True, slots=True)
class Citation:
    source: str
    line: int
    text: str
    unique: bool


def find_citations(answer: str) -> list[tuple[str, str]]:
    return _CITATION.findall(answer)


def resolve(chunk_id: str, quote: str, chunks: tuple[Chunk, ...]) -> Citation | None:
    chunk = assign_ids(chunks).get(chunk_id)
    wanted = quote.strip()
    if chunk is None or not wanted:
        return None

    lines = chunk.text.splitlines()
    hits = _matching_lines(lines, wanted) or _matching_lines(lines, unescape(wanted))
    if not hits:
        return None

    first = hits[0]
    return Citation(
        source=chunk.source,
        line=chunk.start_line + first,
        text=lines[first],
        unique=len(hits) == 1,
    )


def unescape(quote: str) -> str:
    return _MARKDOWN_ESCAPE.sub("", quote)


def _matching_lines(lines: list[str], wanted: str) -> list[int]:
    exact = [index for index, line in enumerate(lines) if line.strip() == wanted]
    if exact:
        return exact

    contained = [index for index, line in enumerate(lines) if wanted in line]
    if contained:
        return contained

    return _wrapped_line(lines, wanted)


def _wrapped_line(lines: list[str], wanted: str) -> list[int]:
    target = " ".join(wanted.split())
    starts: list[int] = []
    squeezed: list[str] = []
    offset = 0

    for line in lines:
        starts.append(offset)
        flat = " ".join(line.split())
        squeezed.append(flat)
        offset += len(flat) + 1

    at = " ".join(squeezed).find(target)
    if at < 0:
        return []

    return [max(index for index, start in enumerate(starts) if start <= at)]
