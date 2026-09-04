from __future__ import annotations

import psycopg
import pytest

from labpilot.store import create_schema

pytestmark = pytest.mark.database


def test_applying_the_schema_again_keeps_the_data(db):
    with db.cursor() as cur:
        cur.execute("insert into artifacts values ('keep', 'n', 'A', 'm', 3)")
    create_schema(db)
    with db.cursor() as cur:
        cur.execute("select count(*) from artifacts where id = 'keep'")
        assert cur.fetchone()[0] == 1
        cur.execute("delete from artifacts where id = 'keep'")


def test_the_database_refuses_a_side_that_is_not_a_or_b(db):
    with db.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("insert into artifacts values ('bad', 'n', 'C', 'm', 3)")


def test_deleting_an_artifact_deletes_its_chunks(db):
    with db.cursor() as cur:
        cur.execute("insert into artifacts values ('cas', 'n', 'B', 'm', 3)")
        cur.execute(
            "insert into chunks values ('cas', 0, 't', '', 's.py', 1, 2, '[1,2,3]')"
        )
        cur.execute("delete from artifacts where id = 'cas'")
        cur.execute("select count(*) from chunks where artifact_id = 'cas'")
        assert cur.fetchone()[0] == 0


def test_one_vector_column_holds_two_different_widths(db):
    with db.cursor() as cur:
        cur.execute("insert into artifacts values ('w', 'n', 'A', 'm', 3)")
        cur.execute("insert into chunks values ('w', 0, 'a', '', 's', 1, 1, '[1,2,3]')")
        cur.execute(
            "insert into chunks values ('w', 1, 'b', '', 's', 1, 1, '[1,2,3,4,5]')"
        )
        cur.execute(
            "select vector_dims(v) from chunks"
            " where artifact_id = 'w' order by chunk_index"
        )
        assert [row[0] for row in cur.fetchall()] == [3, 5]
        cur.execute("delete from artifacts where id = 'w'")


def test_the_test_schema_survives_a_session_reset(db, schema_name):
    # The flake this pins, measured 2026-09-04: Supabase's pooler recycles ONE
    # backend across connections and resets session state. A runtime
    # `set search_path` is wiped by that reset and bare `artifacts` then
    # resolves to the REAL public schema -- silently, because public holds
    # tables of the same name. The fixture therefore sends the search path as a
    # libpq STARTUP option, which a reset restores instead of discarding.
    # `reset all` touches only GUCs, so it cannot disturb prepared statements.
    with db.cursor() as cur:
        cur.execute("reset all")
        cur.execute("select current_schema()")
        assert cur.fetchone()[0] == schema_name


def test_a_dropped_connection_is_reopened(live_connection):
    # The second half of the flake, measured 2026-09-04: the pooler drops a
    # held connection mid-run, and every later test inherited a [BAD] one.
    first = live_connection()
    first.close()

    second = live_connection()
    assert second is not first
    with second.cursor() as cur:
        cur.execute("select 1")
        assert cur.fetchone()[0] == 1
