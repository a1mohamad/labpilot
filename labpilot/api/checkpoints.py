from __future__ import annotations

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from labpilot.ingest import Chunk
from labpilot.llm import Attempt, LLMResult
from labpilot.store import ArtifactRecord, StoredArtifact

SAVED_TYPES = [Chunk, ArtifactRecord, StoredArtifact, Attempt, LLMResult]
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


def open_saver(conn: psycopg.Connection) -> PostgresSaver:
    return PostgresSaver(conn, serde=SERDE)


def prune(conn: psycopg.Connection, thread_id: str) -> None:
    conn.execute(PRUNE, {"thread": thread_id})
