from __future__ import annotations

import os
import secrets
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
import pytest
from dotenv import load_dotenv

from labpilot.store import connect, create_schema, database_url

# One schema PER RUN, never a shared name. Measured 2026-09-05: two test runs
# against the same database - a terminal and the VS Code Testing panel, or two
# terminals - each ran `drop schema ... cascade` on the SAME schema, so one run
# deleted the other's tables mid-test. Reproduced on demand by starting two
# pytest processes at once: both failed, with `relation "chunks" does not
# exist`, writes that read back empty, and duplicate primary keys.
#
# The name carries the pid so a leftover schema can be traced to the run that
# made it. Nothing here ever drops a schema it did not create - that is what
# made the shared name unsafe.
TEST_SCHEMA = f"labpilot_test_{os.getpid()}_{secrets.token_hex(3)}"


def with_search_path(url: str, schema: str) -> str:
    # The search path MUST arrive as a libpq STARTUP option, never as a runtime
    # `set search_path`. Measured 2026-09-04 against the real project: Supabase
    # puts a pooler (Supavisor) in front of Postgres, and 12 separate client
    # connections across 6 suite runs all landed on ONE backend, pid 833757.
    # Recycling that backend issues RESET ALL / DISCARD ALL, which throws away
    # a runtime SET but restores a startup option:
    #
    #   runtime SET     -> after RESET ALL: '"$user", public, extensions'  LOST
    #   startup option  -> after RESET ALL: 'labpilot_test,public'         KEPT
    #
    # With the runtime SET the loss was SILENT, because bare `artifacts` then
    # resolved to the real public schema. That was the flake.
    #
    # `public` stays on the path on purpose: the vector TYPE lives in public on
    # this project, so dropping it makes `v vector` fail to resolve.
    parts = urlsplit(url)
    option = quote(f"-c search_path={schema},public", safe="")
    query = f"{parts.query}&options={option}" if parts.query else f"options={option}"
    return urlunsplit(parts._replace(query=query))


@pytest.fixture(scope="session")
def schema_url() -> Iterator[str]:
    load_dotenv(".env")
    if not os.environ.get("DATABASE_URL", "").strip():
        pytest.skip("needs DATABASE_URL - a live Postgres with pgvector")

    url = with_search_path(database_url(), TEST_SCHEMA)
    with connect(url) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {TEST_SCHEMA} cascade")
            cur.execute(f"create schema {TEST_SCHEMA}")
            cur.execute("select current_schema()")
            landed = cur.fetchone()[0]

        # Refuse to run rather than create the tables somewhere else. Without
        # this the tests write to the REAL schema and still report green.
        if landed != TEST_SCHEMA:
            raise RuntimeError(
                f"test isolation failed: statements would land in {landed!r}, "
                f"not {TEST_SCHEMA!r}. Refusing to touch the real schema."
            )
        create_schema(conn)

    yield url

    with connect(database_url()) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {TEST_SCHEMA} cascade")


@pytest.fixture(scope="session")
def schema_name() -> str:
    return TEST_SCHEMA


def _responds(conn: psycopg.Connection) -> bool:
    if conn.closed:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("select 1")
    except psycopg.Error:
        return False
    return True


@pytest.fixture(scope="session")
def live_connection(schema_url: str) -> Iterator[Callable[[], psycopg.Connection]]:
    # "Pre-ping": check the connection before handing it out, and reopen it if
    # the pooler has dropped it. Measured 2026-09-04: a pooled connection held
    # across a module really does die mid-run ("server closed the connection
    # unexpectedly"), and every later test then inherited a [BAD] connection.
    # Reopening per TEST instead would be correct too, but costs ~2s each on
    # this link, so the ping (~0.3s) buys the same safety far cheaper.
    with ExitStack() as stack:
        held: list[psycopg.Connection] = []

        def opened() -> psycopg.Connection:
            conn = stack.enter_context(connect(schema_url))
            conn.autocommit = True
            held.append(conn)
            return conn

        def current() -> psycopg.Connection:
            if held and _responds(held[-1]):
                return held[-1]
            conn = opened()
            # The pooler can hand back a connection that is already dead, so
            # a fresh one still has to prove it answers before it is used.
            return conn if _responds(conn) else opened()

        yield current


@pytest.fixture
def db(live_connection: Callable[[], psycopg.Connection]) -> psycopg.Connection:
    # A pooled connection can die between the ping and the next statement, so
    # the first real statement of every test is also its retry point. One retry
    # only: a second failure is a genuine problem and must be reported.
    for attempt in (1, 2):
        conn = live_connection()
        try:
            return _emptied(conn)
        except psycopg.Error:
            if attempt == 2:
                raise
            conn.close()
    raise AssertionError("unreachable")


def _emptied(conn: psycopg.Connection) -> psycopg.Connection:
    with conn.cursor() as cur:
        # Start every test from an empty corpus, so no test can depend on rows
        # another one left behind; chunks go by cascade. DELETE, not TRUNCATE:
        # truncate needs ACCESS EXCLUSIVE, which conflicts with even a SELECT,
        # and a pooled backend still holding a lock made it block until the
        # 2min statement_timeout - the integration folder went 28s -> 238s.
        cur.execute("delete from artifacts")
    return conn
