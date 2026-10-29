from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg_pool import ConnectionPool

from labpilot.agent import Claim, CodeFinding, Correspondence, Finding, Plan, Query
from labpilot.ingest import Chunk
from labpilot.llm import Attempt, LLMResult
from labpilot.store import ArtifactRecord, StoredArtifact

SAVED_TYPES = [
    Chunk,
    ArtifactRecord,
    StoredArtifact,
    Plan,
    Query,
    Claim,
    Correspondence,
    Finding,
    CodeFinding,
    Attempt,
    LLMResult,
]
SERDE = JsonPlusSerializer(allowed_msgpack_modules=SAVED_TYPES)

PRUNE = """
with newest as (
    select checkpoint_id, checkpoint
    from checkpoints
    where thread_id = %(thread)s and checkpoint_ns = ''
    order by checkpoint_id desc
    limit 1
),
old_copies as (
    delete from checkpoints c
    using newest n
    where c.thread_id = %(thread)s and c.checkpoint_id <> n.checkpoint_id
),
old_writes as (
    delete from checkpoint_writes w
    using newest n
    where w.thread_id = %(thread)s and w.checkpoint_id <> n.checkpoint_id
)
delete from checkpoint_blobs b
using newest n
where b.thread_id = %(thread)s
  and not exists (
  select 1
  from jsonb_each_text(n.checkpoint -> 'channel_versions') v
  where v.key = b.channel and v.value = b.version
  )
"""
CHAT_TABLES = (
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
)


def lock_tables(conn: psycopg.Connection) -> None:
    for table in CHAT_TABLES:
        conn.execute(f"alter table {table} enable row level security")


class _OneAtATime:
    """A cursor whose `executemany` sends one statement, waits, and sends the next.

    psycopg runs `executemany` in PIPELINE MODE, and libpq has a bug there: when
    a large message is sent over SSL and the network takes it in several pieces,
    the next message is added to the output while the first write is still being
    retried, and OpenSSL refuses with `SSL error: bad length` (PostgreSQL bug
    report #18907). Everything else is passed to the real cursor.
    """

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def executemany(self, query: Any, params_seq: Iterable[Any]) -> None:
        for params in params_seq:
            self._cursor.execute(query, params)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _SafeSaver(PostgresSaver):
    """The Postgres saver with no pipeline mode, for a checkpoint of a real size.

    Found by the closing review of slice 5 (2026-10-21). A chat on the search path
    saves about 150 KB (the prompt, the text of the chunks, the report). Sent in
    pipeline mode, the save failed in 9 of 15 runs of the same two-message chat
    on one afternoon (`SSL error: bad length`, or `connection not in pipeline
    mode`), and in none of the runs of the next hour: it depends on the network,
    so only the unit tests of this function can hold the rule. The stuffed path
    never failed because its checkpoint is tiny. Without pipeline mode the saver
    keeps one transaction with the same statements. The price is a few more round
    trips of about 0.12 s each, on a report that takes minutes.
    """

    def __init__(self, conn: psycopg.Connection | ConnectionPool) -> None:
        super().__init__(conn, serde=SERDE)
        self.supports_pipeline = False

    @contextmanager
    def _cursor(self, *, pipeline: bool = False) -> Iterator[Any]:
        with super()._cursor(pipeline=pipeline) as cursor:
            yield _OneAtATime(cursor)


def open_saver(conn: psycopg.Connection | ConnectionPool) -> PostgresSaver:
    return _SafeSaver(conn)


def prune(place: psycopg.Connection | ConnectionPool, thread_id: str) -> None:
    if isinstance(place, ConnectionPool):
        with place.connection() as conn:
            conn.execute(PRUNE, {"thread": thread_id})
        return
    place.execute(PRUNE, {"thread": thread_id})
