from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256

from labpilot.ingest import (
    Chunk,
    LoaderError,
    LooksGenerated,
    NotUtf8Text,
    Side,
    chunk_file,
)
from labpilot.sources import Source, walk


def _newest_owner(source: Source, *, side: Side) -> dict[str, str]:
    """For every distinct chunk text, the NEWEST file that holds it.

    A repository really does hold the same content several times, and the copies
    are the ones our own fixtures had to exclude by hand: `lung` was 34.8%
    duplicate chunks from mlflow artifact copies, `pydantic` 6.6% from mypy
    outputs, and the user's `titanic` folder holds THREE versions of one
    notebook plus Jupyter's auto-save - 39.1% duplicate text, measured.

    NEWEST, not first, and that is the whole point. Sorted-path order would have
    kept `titanic_V2.ipynb` over `titanic_analysisV2.ipynb`, so a divergence
    report would compare the paper against code the user replaced months ago -
    confidently, with a citation. For a tool whose job is explaining why two
    things differ, answering from a stale copy is the worst failure it has.

    IDS STILL COME FROM PATH ORDER. mtime decides only WHICH copy survives,
    never the order chunks are numbered in: a fresh clone gives every file the
    same mtime, so ordering by it would make chunk ids differ between machines -
    the determinism `_paths` sorts for.

    The cost is one extra chunking pass. MEASURED: 0.9s for pytest's 10,064
    chunks, against an embed of several minutes. Only hashes are kept, so the
    streaming rule is untouched.
    """
    owners: dict[str, tuple[float, str]] = {}
    for found in walk(source):
        try:
            pieces = chunk_file(
                found.path, side=side, artifact_id=source.name, source=found.relpath
            )
            mtime = found.path.stat().st_mtime
        except (LoaderError, OSError):
            continue

        for piece in pieces:
            key = sha256(piece.text.encode("utf-8")).hexdigest()
            best = owners.get(key)
            if best is None or mtime > best[0]:
                owners[key] = (mtime, found.relpath)
    return {key: relpath for key, (_, relpath) in owners.items()}


def chunk_source(source: Source, *, side: Side) -> Iterator[Chunk]:
    owners = _newest_owner(source, side=side)
    seen: set[str] = set()
    index = 0
    for found in walk(source):
        try:
            pieces = chunk_file(
                found.path,
                side=side,
                artifact_id=source.name,
                source=found.relpath,
            )
        except NotUtf8Text:
            source.skip("not utf-8")
            continue
        except LooksGenerated:
            source.skip("generated or minified")
            continue
        except LoaderError:
            source.skip("unreadable document")
            continue
        except OSError:
            source.skip("unreadable file")
            continue

        for piece in pieces:
            # A chunk this file does not OWN is a copy of one we are keeping
            # elsewhere, and a second copy buys nothing: it cannot answer a
            # question the first cannot, and it spends embedding budget, a
            # storage row and a slot in every future search window.
            #
            # The cost is real and small: two modules that genuinely define the
            # same thing are now cited once, at the newest of them.
            key = sha256(piece.text.encode("utf-8")).hexdigest()
            if owners.get(key) != found.relpath or key in seen:
                source.skip("duplicate of a newer copy")
                continue
            seen.add(key)

            # chunk_index restarts at 0 in every file, because chunk_file
            # numbers what IT produced. The chunks table's primary key is
            # (artifact_id, chunk_index), so a repository of twenty files would
            # collide on the second one - and prompt ids are positional, so
            # even without a database two files would both claim B-0.
            yield replace(piece, chunk_index=index)
            index += 1
