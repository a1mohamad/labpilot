from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

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
        kwargs={"autocommit": True, "connection_timeout": CONNECT_TIMEOUT},
        check=ConnectionPool.check_connection,
        open=False,
    )


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
