from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import psycopg

from labpilot.store.defaults import CONNECT_TIMEOUT
from labpilot.store.errors import ConnectionFailed, NotConfigured

DATABASE_URL_ENV = "DATABASE_URL"
SCHEMA = Path(__file__).parent / "schema.sql"


def database_url() -> str:
    url = os.environ.get(DATABASE_URL_ENV, "").strip()
    if not url:
        raise NotConfigured(f"{DATABASE_URL_ENV} is not set: see .env.example")
    return url


@contextmanager
def connect(url: str | None = None) -> Generator[psycopg.Connection]:
    try:
        opened = psycopg.connect(url or database_url(), connect_timeout=CONNECT_TIMEOUT)
    except psycopg.Error as exc:
        raise ConnectionFailed(f"could not reach theda database: {exc}") from exc

    with opened as conn:
        yield conn


def create_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
