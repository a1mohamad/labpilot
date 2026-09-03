from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from labpilot.store import connect, create_schema

TEST_SCHEMA = "labpilot_test"


@pytest.fixture(scope="module")
def db():
    load_dotenv(".env")
    if not os.environ.get("DATABASE_URL", "").strip():
        pytest.skip("needs DATABASE_URL - a live Postgres with pgvector")

    with connect() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {TEST_SCHEMA} cascade")
            cur.execute(f"create schema {TEST_SCHEMA}")
            cur.execute(f"set search_path to {TEST_SCHEMA}, public")
        create_schema(conn)
        yield conn
        with conn.cursor() as cur:
            cur.execute(f"drop schema if exists {TEST_SCHEMA} cascade")
