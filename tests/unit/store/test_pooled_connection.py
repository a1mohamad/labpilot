"""A connection is held for a query, never for a whole question (R16)."""

from contextlib import contextmanager

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from labpilot.store import ConnectionFailed, PooledConnection


class FakeCursor:
    pass


class FakeConnection:
    def __init__(self, error=None, closed=False):
        self.error, self.closed, self.asked = error, closed, []

    def execute(self, query, params=None):
        self.asked.append((query, params))
        if self.error:
            raise self.error
        return "rows"

    @contextmanager
    def cursor(self, **kwargs):
        yield FakeCursor()


class FakePool:
    def __init__(self, *conns, closed=False):
        self.conns, self.closed = list(conns), closed
        self.out = 0

    def open(self, wait):
        self.closed = False

    @contextmanager
    def connection(self, timeout=None):
        if not self.conns:
            raise PoolTimeout("no connection")
        self.out += 1
        try:
            yield self.conns.pop(0)
        finally:
            self.out -= 1


def test_the_connection_is_given_back_after_each_query():
    pool = FakePool(FakeConnection(), FakeConnection())
    conn = PooledConnection(pool)

    assert conn.execute("select 1") == "rows"
    assert pool.out == 0
    with conn.cursor() as cur:
        assert isinstance(cur, FakeCursor) and pool.out == 1
    assert pool.out == 0


def test_a_closed_pool_is_opened_by_the_first_query():
    pool = FakePool(FakeConnection(), closed=True)

    PooledConnection(pool).execute("select 1")

    assert not pool.closed


def test_a_query_is_sent_again_when_its_connection_died():
    dead = FakeConnection(psycopg.OperationalError("EOF"), closed=True)
    good = FakeConnection()

    assert PooledConnection(FakePool(dead, good)).execute("q", ("p",)) == "rows"
    assert good.asked == [("q", ("p",))]


def test_a_query_is_sent_again_only_once():
    dead = [FakeConnection(psycopg.OperationalError("EOF"), True) for _ in range(3)]
    pool = FakePool(*dead)

    with pytest.raises(psycopg.OperationalError):
        PooledConnection(pool).execute("q")
    assert len(pool.conns) == 1


def test_an_error_on_a_living_connection_is_not_sent_again():
    timeout = FakeConnection(psycopg.OperationalError("statement timeout"))
    pool = FakePool(timeout, FakeConnection())

    with pytest.raises(psycopg.OperationalError):
        PooledConnection(pool).execute("q")
    assert len(pool.conns) == 1


def test_a_database_nobody_can_reach_is_our_own_error():
    with pytest.raises(ConnectionFailed):
        PooledConnection(FakePool()).execute("q")
    with pytest.raises(ConnectionFailed), PooledConnection(FakePool()).cursor():
        pass
