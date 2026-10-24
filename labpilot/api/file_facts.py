import logging
import threading
from collections.abc import Sequence

import psycopg

from labpilot.ingest import Chunk
from labpilot.prompts import OPENING_CHARS, build_map
from labpilot.retrieval import unused_definitions
from labpilot.store import StoreError, read_chunks, read_headers

logger = logging.getLogger(__name__)

# The outline the query writer gets. Small on purpose: it rides on every retry
# of every absent claim.
OUTLINE_TOKENS = 3_000


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

    def unused(self, artifact_id: str) -> dict[str, str]:
        with self._lock:
            if artifact_id not in self._unused:
                try:
                    stored = read_chunks(self._conn, artifact_id)
                    found = unused_definitions(
                        [(chunk.header, chunk.text) for chunk in stored]
                    )
                except StoreError:
                    logger.warning("no usage facts of %s", artifact_id, exc_info=True)
                    found = {}
                self._unused[artifact_id] = found
            return self._unused[artifact_id]

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
