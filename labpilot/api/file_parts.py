import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import psycopg

from labpilot.api.errors import UnknownArtifactId
from labpilot.api.reading import as_chunk
from labpilot.ingest import Chunk
from labpilot.prompts import groups_of, whole_files
from labpilot.store import StoreError, UnknownArtifact, read_chunks
from labpilot.tokens import estimate_tokens

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FileParts:
    """The parts of one stored file that a step reads, in their order.

    A prompt numbers the parts it shows ([part 0], [part 1], ...), and an answer
    names a part by that number. `texts` and `sources` are kept in the same
    order, so number n is the same part in all three.
    """

    chunks: tuple[Chunk, ...]
    texts: tuple[str, ...]
    sources: tuple[str, ...]

    @classmethod
    def of(cls, chunks: Sequence[Chunk]) -> "FileParts":
        return cls(
            chunks=tuple(chunks),
            texts=tuple(f"{chunk.header}\n{chunk.text}" for chunk in chunks),
            sources=tuple(chunk.header or chunk.source for chunk in chunks),
        )

    @property
    def tokens(self) -> int:
        return sum(estimate_tokens(text) for text in self.texts)

    @property
    def text(self) -> str:
        return "\n\n".join(self.texts)

    def groups(self, target: int, *, by_file: bool = False) -> list["FileParts"]:
        """The parts in groups of about `target` tokens; with `by_file` a small
        file is never split between two groups (D94)."""
        files = [chunk.source for chunk in self.chunks] if by_file else None
        return [
            FileParts.of([self.chunks[i] for i in ids])
            for ids in groups_of(self.texts, target, files=files)
        ]

    def only(self, keep: Callable[[Chunk], bool]) -> "FileParts":
        return FileParts.of([chunk for chunk in self.chunks if keep(chunk)])

    def chunk_for(self, source: str) -> Chunk | None:
        """The part a finding points at, by the source the prompt gave it."""
        for chunk, named in zip(self.chunks, self.sources, strict=True):
            if named == source:
                return chunk
        return None


def read_parts(
    conn: psycopg.Connection,
    artifact_id: str,
    *,
    limit: int | None,
    error: type[Exception],
) -> FileParts:
    """The parts of a stored file, in whole files up to `limit` tokens (D94).

    A file that does not fit is skipped and the log says how much was read. A
    missing artifact is the caller's mistake (404); a dropped connection is
    raised as `error`, which the step turns into "no findings".
    """
    try:
        stored = read_chunks(conn, artifact_id)
    except UnknownArtifact as exc:
        raise UnknownArtifactId(str(exc)) from exc
    except (StoreError, psycopg.Error) as exc:
        raise error(f"could not read {artifact_id}: {exc}") from exc

    side = artifact_id[:1]
    chunks = [as_chunk(part, side, artifact_id) for part in stored]
    if limit is not None:
        texts = [f"{part.header}\n{part.text}" for part in stored]
        names = [part.source for part in stored]
        picked = whole_files(texts, names, limit)
        if len(picked) < len(chunks):
            logger.warning(
                "%s is read in part: %d of %d parts, %d of %d files",
                artifact_id,
                len(picked),
                len(chunks),
                len({names[i] for i in picked}),
                len(set(names)),
            )
        chunks = [chunks[i] for i in picked]
    if not chunks:
        raise error(f"{artifact_id} has no parts to read")
    return FileParts.of(chunks)
