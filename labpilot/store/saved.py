from __future__ import annotations

import psycopg

# D104: what a step made for some files, saved once and read again by the next
# message or the next chat with the same files. The store keeps bytes it cannot
# read: `api/` turns the values into bytes and back.
_READ = "select kind, payload from saved_results where key = %s"

_WRITE = """
    insert into saved_results (key, kind, payload, artifact_a, artifact_b)
    values (%s, %s, %s, %s, %s)
    on conflict (key) do update set
        kind = excluded.kind,
        payload = excluded.payload,
        created_at = now()
"""


def read_saved(conn: psycopg.Connection, key: str) -> tuple[str, bytes] | None:
    """The type name and the bytes saved under `key`, or None if none are."""
    row = conn.execute(_READ, (key,)).fetchone()
    if row is None:
        return None
    return row[0], bytes(row[1])


def write_saved(
    conn: psycopg.Connection,
    key: str,
    kind: str,
    payload: bytes,
    *,
    artifacts: tuple[str, ...],
) -> None:
    """Save `payload` under `key`, tied to one or two stored artifacts.

    The rows go with the artifacts (`on delete cascade`), so a file stored
    again (same id, rows written again) is analysed again and never answered
    from what its old rows said.
    """
    if not 1 <= len(artifacts) <= 2:
        raise ValueError("a saved result belongs to one or two artifacts")
    first, *rest = artifacts
    conn.execute(_WRITE, (key, kind, payload, first, rest[0] if rest else None))
