import logging
import threading
from collections.abc import Sequence

import psycopg

from labpilot.api.reading import as_chunk
from labpilot.ingest import Chunk
from labpilot.prompts import OPENING_CHARS, build_map
from labpilot.retrieval import (
    constant_definitions,
    constants_named,
    unused_definitions,
)
from labpilot.store import StoredChunk, StoreError, read_chunks, read_headers

logger = logging.getLogger(__name__)

# The outline the query writer gets. Small on purpose: it rides on every retry
# of every absent claim.
OUTLINE_TOKENS = 3_000

# At most this many parts that SET a constant are added to a check (see expand).
MAX_DEFINITIONS = 3


class FileFacts:
    """What a WHOLE stored file says, read at most once for one question.

    A check and a new query see a few parts of the other file. Two things only
    the whole file can show: its outline (the names it really uses, R17) and
    the functions it defines and never names again (R8). Many checks run at the
    same time, so the reads are guarded and kept.
    """

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()
        self._outlines: dict[str, str] = {}
        self._unused: dict[str, dict[str, str]] = {}
        self._stored: dict[str, tuple[StoredChunk, ...]] = {}

    def outline(self, artifact_id: str) -> str:
        with self._lock:
            if artifact_id not in self._outlines:
                try:
                    headers = read_headers(
                        self._conn, artifact_id, opening_chars=OPENING_CHARS
                    )
                    text = build_map({"B": headers}, budget=OUTLINE_TOKENS)
                except StoreError:
                    logger.warning("no outline of %s", artifact_id, exc_info=True)
                    text = ""
                self._outlines[artifact_id] = text
            return self._outlines[artifact_id]

    def _parts(self, artifact_id: str) -> tuple[StoredChunk, ...]:
        # Called with the lock held.
        if artifact_id not in self._stored:
            try:
                self._stored[artifact_id] = read_chunks(self._conn, artifact_id)
            except StoreError:
                logger.warning("could not read %s whole", artifact_id, exc_info=True)
                self._stored[artifact_id] = ()
        return self._stored[artifact_id]

    def unused(self, artifact_id: str) -> dict[str, str]:
        with self._lock:
            if artifact_id not in self._unused:
                stored = self._parts(artifact_id)
                self._unused[artifact_id] = unused_definitions(
                    [(chunk.header, chunk.text) for chunk in stored]
                )
            return self._unused[artifact_id]

    def expand(self, chunks: Sequence[Chunk]) -> tuple[Chunk, ...]:
        """The parts, plus the parts that SET the constants they only use.

        A search for "gradients are clipped at 1.0" finds the line that USES
        `self.config.CLIP_NORM` and not the line `CLIP_NORM = 1.5`, so the
        check said "absent" (2026-10-25, the E5 run: clipping, the unfreeze
        epoch and the split). This is "go to definition", as a code agent does
        it: for each constant the parts name and do not set, the part that
        sets it is added, at most MAX_DEFINITIONS of them.
        """
        if not chunks:
            return tuple(chunks)
        added: list[Chunk] = []
        held = {(chunk.artifact_id, chunk.chunk_index) for chunk in chunks}
        for artifact_id in dict.fromkeys(chunk.artifact_id for chunk in chunks):
            with self._lock:
                stored = self._parts(artifact_id)
            by_index = {part.chunk_index: part for part in stored}
            setters = constant_definitions(
                [(part.chunk_index, part.text) for part in stored]
            )
            own = [chunk for chunk in chunks if chunk.artifact_id == artifact_id]
            set_here = set(constant_definitions([(0, chunk.text) for chunk in own]))
            for chunk in own:
                for name in constants_named(chunk.text):
                    index = setters.get(name)
                    if name in set_here or index is None:
                        continue
                    if (artifact_id, index) in held:
                        continue
                    if len(added) >= MAX_DEFINITIONS:
                        return (*chunks, *added)
                    held.add((artifact_id, index))
                    added.append(as_chunk(by_index[index], chunk.side, artifact_id))
        return (*chunks, *added)

    def facts_for(self, chunks: Sequence[Chunk]) -> str:
        """One line for each function these parts define that is never named
        again anywhere in their file."""
        lines: list[str] = []
        for artifact_id in dict.fromkeys(chunk.artifact_id for chunk in chunks):
            unused = self.unused(artifact_id)
            headers = {
                chunk.header for chunk in chunks if chunk.artifact_id == artifact_id
            }
            for name, header in unused.items():
                if header in headers:
                    lines.append(
                        f"`{name}` (defined in {header}) is never called or named "
                        "anywhere else in this file."
                    )
        return "\n".join(lines)
