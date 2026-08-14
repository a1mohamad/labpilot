from __future__ import annotations

import re
from dataclasses import dataclass

from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids

_CITATION = re.compile(r'\[([AB]-\d+)\s+"(.*?)"\]')


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
    hits = _matching_lines(lines, wanted)
    if not hits:
        return None

    first = hits[0]
    return Citation(
        source=chunk.source,
        line=chunk.start_line + first,
        text=lines[first],
        unique=len(hits) == 1,
    )


def _matching_lines(lines: list[str], wanted: str) -> list[int]:
    exact = [index for index, line in enumerate(lines) if line.strip() == wanted]
    if exact:
        return exact
    return [index for index, line in enumerate(lines) if wanted in line]
