"""A whole question over a real pool, with no connection held between queries (R16).

The unit tests use a fake pool. What only a real one can show: that rows can be
read after their connection went back, that the read functions of the store take
the pooled connection as it is, and that steps running together share the pool.
"""

import threading

import pytest

from labpilot.api import asking
from labpilot.store import (
    PooledConnection,
    make_pool,
    measure,
    read_chunks,
    read_headers,
    read_saved,
    search,
    write_saved,
)
from tests.integration.test_ask import FakeClient, stored

pytestmark = pytest.mark.database


@pytest.fixture
def pool(schema_url):
    made = make_pool(schema_url)
    yield made
    made.close()


def test_the_store_reads_the_same_through_the_pool(db, pool):
    b = stored(db, "B", parts=4, words=20)
    write_saved(db, "bugs:p", "msgpack", b"x", artifacts=(b,))
    conn = PooledConnection(pool)

    assert measure(conn, b) == measure(db, b)
    assert read_chunks(conn, b) == read_chunks(db, b)
    assert read_headers(conn, b) == read_headers(db, b)
    assert read_saved(conn, "bugs:p") == ("msgpack", b"x")
    found = measure(db, b).artifact
    vector = (1.0,) + (0.0,) * (found.dim - 1)
    hits = search(conn, b, vector, model=found.embedding_model)
    assert hits == search(db, b, vector, model=found.embedding_model)


def test_a_write_through_the_pool_is_really_committed(db, pool):
    b = stored(db, "B", parts=2, words=20)

    write_saved(PooledConnection(pool), "bugs:w", "msgpack", b"kept", artifacts=(b,))

    assert read_saved(db, "bugs:w") == ("msgpack", b"kept")


def test_no_connection_is_out_while_a_model_answers(db, pool):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    out = []

    class Watching(FakeClient):
        def generate(self, *args, **kwargs):
            stats = pool.get_stats()
            out.append(stats["pool_size"] - stats["pool_available"])
            return super().generate(*args, **kwargs)

    answer = asking.ask(
        PooledConnection(pool), a, b, question="why?", client=Watching(), pool=pool
    )

    assert answer.result.text
    # The answer itself is written when no other step runs.
    assert out[-1] == 0


def test_a_chat_is_saved_over_the_pool_with_no_shared_connection(db, pool, chat_tables):
    b = stored(db, "B", parts=3, words=20)
    conn = PooledConnection(pool)

    for question in ("first?", "second?"):
        asking.ask(
            conn,
            "",
            b,
            question=question,
            client=FakeClient(),
            thread_id="pooled-chat",
            pool=pool,
        )

    copies = db.execute(
        "select count(*) from checkpoints where thread_id = 'pooled-chat'"
    ).fetchone()
    assert copies == (1,)


def test_many_steps_at_once_wait_for_a_connection_and_none_fails(db, pool):
    b = stored(db, "B", parts=3, words=20)
    conn, done = PooledConnection(pool), []

    def read():
        done.append(len(read_chunks(conn, b)))

    threads = [threading.Thread(target=read) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)

    assert done == [3] * 20
