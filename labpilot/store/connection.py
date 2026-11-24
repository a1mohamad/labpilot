from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout

from labpilot.store.defaults import CONNECT_TIMEOUT, POOL_SIZE
from labpilot.store.errors import ConnectionFailed, NotConfigured

DATABASE_URL_ENV = "DATABASE_URL"
SCHEMA = Path(__file__).parent / "schema.sql"


def database_url() -> str:
    url = os.environ.get(DATABASE_URL_ENV, "").strip()
    if not url:
        raise NotConfigured(f"{DATABASE_URL_ENV} is not set: see .env.example")
    return url


@contextmanager
def connect(
    url: str | None = None, *, autocommit: bool = False
) -> Generator[psycopg.Connection]:
    try:
        opened = psycopg.connect(
            url or database_url(),
            connect_timeout=CONNECT_TIMEOUT,
            autocommit=autocommit,
        )
    except psycopg.Error as exc:
        raise ConnectionFailed(f"could not reach the database: {exc}") from exc

    with opened as conn:
        yield conn


def make_pool(url: str | None = None) -> ConnectionPool:
    return ConnectionPool(
        url or database_url(),
        min_size=POOL_SIZE,
        max_size=POOL_SIZE,
        kwargs={"autocommit": True, "connect_timeout": CONNECT_TIMEOUT},
        check=ConnectionPool.check_connection,
        open=False,
    )


class PooledConnection:
    """Takes a connection from the pool for EACH query and gives it back at once.

    A question can take minutes, most of them spent waiting for a model. One
    connection held all that time sits idle, the server may close it, and it is
    one of the 15 clients the database allows (R16). This has the two methods
    the read functions of the store use, so it is handed to them as they are.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @contextmanager
    def _borrow(self) -> Generator[psycopg.Connection]:
        if self._pool.closed:
            self._pool.open(wait=False)
        try:
            with self._pool.connection(timeout=CONNECT_TIMEOUT) as conn:
                yield conn
        except PoolTimeout as exc:
            raise ConnectionFailed(f"could not reach the database: {exc}") from exc

    def execute(self, query: Any, params: Any = None) -> psycopg.Cursor:
        # The rows are already here when execute returns, so they can be read
        # after the connection went back. Every query sent this way is a read or
        # an upsert, so it can be sent again when the connection died under it.
        for attempt in range(2):
            with self._borrow() as conn:
                try:
                    return conn.execute(query, params)
                except psycopg.OperationalError:
                    if attempt or not conn.closed:
                        raise
        raise AssertionError("unreachable")

    @contextmanager
    def cursor(self, **kwargs: Any) -> Generator[psycopg.Cursor]:
        with self._borrow() as conn, conn.cursor(**kwargs) as cur:
            yield cur


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
