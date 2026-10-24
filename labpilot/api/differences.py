import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import psycopg

from labpilot.agent import (
    A_SILENT,
    DIFFERENCES_TOOL_NAME,
    CodeFinding,
    DifferencesError,
    differences_schema,
    read_code_findings,
)
from labpilot.api.errors import UnknownArtifactId
from labpilot.api.file_facts import FileFacts
from labpilot.api.reading import as_chunk
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult, Tool
from labpilot.prompts import (
    A_WHOLE_TOKENS,
    DIFFERENCES_GROUP_TOKENS,
    DIFFERENCES_MAX_TOKENS,
    DIFFERENCES_VERSION,
    SCAN_TOKENS,
    build_differences_prompt,
    groups_of,
)
from labpilot.store import StoreError, UnknownArtifact, read_chunks
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)

# The words of a code finding that comes from the whole file, not from a model:
# certain, short, and kept before the model's lines when room is short.
NEVER_CALLED = "is defined in B and never called"

TOOL_DESCRIPTION = "List what B does differently from A or that A does not say."

# The groups are asked at the same time, at most this many at once.
GROUPS_AT_ONCE = 4


def _problem(
    result: LLMResult, *, sources: Sequence[str], texts: Sequence[str]
) -> str | None:
    if result.arguments is None:
        return "no arguments"
    try:
        read_code_findings(result.arguments, sources, texts)
    except DifferencesError as exc:
        return str(exc)
    return None


def _def_line(text: str, name: str) -> str:
    for line in text.splitlines():
        if f"def {name}" in line:
            return line.strip()
    return name


def make_difference_finder(
    conn: psycopg.Connection, client: LLMClient, facts: FileFacts
) -> Callable[[str, str], tuple[CodeFinding, ...]]:
    tool = Tool(
        name=DIFFERENCES_TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters=differences_schema(),
    )

    def one_group(
        a_parts: list[str], chunks: list[Chunk]
    ) -> tuple[CodeFinding, ...] | None:
        texts = [f"{chunk.header}\n{chunk.text}" for chunk in chunks]
        sources = [chunk.header or chunk.source for chunk in chunks]
        try:
            result = client.generate(
                build_differences_prompt(a_parts, texts),
                max_tokens=DIFFERENCES_MAX_TOKENS,
                tool=tool,
                problem_with=partial(_problem, sources=sources, texts=texts),
            )
        except AllFreeTiersExhausted as exc:
            logger.warning("no tier read a group of B (%d)", len(exc.attempts))
            return None
        if result.arguments is None:
            return None
        found = read_code_findings(result.arguments, sources, texts, chunks)
        logger.info(
            "differences v%d by %s (tier %s): %d from %d parts",
            DIFFERENCES_VERSION,
            result.model,
            result.tier,
            len(found),
            len(chunks),
        )
        return found

    def find(a_id: str, b_id: str) -> tuple[CodeFinding, ...]:
        try:
            a_stored = read_chunks(conn, a_id)
            b_stored = read_chunks(conn, b_id)
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc
        except (StoreError, psycopg.Error) as exc:
            # A dropped connection must not stop the answer: the scan is a
            # safety net (seen on 2026-10-24, "server closed the connection").
            raise DifferencesError(f"could not read the files: {exc}") from exc

        a_parts = [f"{part.header}\n{part.text}" for part in a_stored]
        if sum(estimate_tokens(part) for part in a_parts) > A_WHOLE_TOKENS:
            raise DifferencesError("the reference is too big to put beside B")

        # The parts of B in order, up to what one question may scan.
        chunks: list[Chunk] = []
        spent = 0
        for stored in b_stored:
            cost = estimate_tokens(f"{stored.header}\n{stored.text}")
            if spent + cost > SCAN_TOKENS:
                break
            chunks.append(as_chunk(stored, "B", b_id))
            spent += cost
        if len(chunks) < len(b_stored):
            logger.warning(
                "B is scanned only in part: %d of %d parts", len(chunks), len(b_stored)
            )
        if not chunks:
            raise DifferencesError("B has no parts to read")

        texts = [f"{chunk.header}\n{chunk.text}" for chunk in chunks]
        groups = groups_of(texts, DIFFERENCES_GROUP_TOKENS)
        with ThreadPoolExecutor(min(len(groups), GROUPS_AT_ONCE)) as pool:
            answers = list(
                pool.map(
                    lambda ids: one_group(a_parts, [chunks[i] for i in ids]), groups
                )
            )
        given = [answer for answer in answers if answer is not None]
        if not given:
            raise DifferencesError(f"no tier read any of {len(groups)} groups of B")

        # A fact no group can see: what B defines and never names again.
        by_header = {chunk.header: chunk for chunk in chunks}
        unused = [
            CodeFinding(
                f"`{name}` {NEVER_CALLED} or named anywhere "
                "else in B (a framework may still call it by name)",
                header,
                _def_line(by_header[header].text, name)
                if header in by_header
                else name,
                A_SILENT,
                by_header.get(header),
            )
            for name, header in facts.unused(b_id).items()
        ]
        return tuple(found for answer in given for found in answer) + tuple(unused)

    return find
