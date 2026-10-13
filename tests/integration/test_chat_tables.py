import pytest

from labpilot.api.checkpoints import CHAT_TABLES, lock_tables

pytestmark = pytest.mark.database


def tables(db, where: str) -> set[str]:
    with db.cursor() as cur:
        cur.execute(
            "select tablename from pg_tables"
            f" where schemaname = current_schema() and {where}"
        )
        return {row[0] for row in cur.fetchall()}


def test_the_list_names_every_table_the_saver_creates(db, chat_tables):
    assert tables(db, "tablename like 'checkpoint%'") == set(CHAT_TABLES)


def test_locking_turns_row_level_security_on_for_every_chat_table(db, chat_tables):
    lock_tables(db)

    assert set(CHAT_TABLES) <= tables(db, "rowsecurity")
