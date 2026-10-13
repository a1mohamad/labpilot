import re

from labpilot.store.connection import SCHEMA


def test_every_table_the_schema_creates_also_turns_row_level_security_on():
    sql = SCHEMA.read_text(encoding="utf-8")
    created = re.findall(r"create table if not exists (\w+)", sql, re.IGNORECASE)
    locked = re.findall(
        r"alter table (\w+) enable row level security", sql, re.IGNORECASE
    )

    assert created, "the schema creates no table, so this test checks nothing"
    assert set(created) <= set(locked), sorted(set(created) - set(locked))
