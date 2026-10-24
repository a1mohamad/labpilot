import threading

from labpilot.api import file_facts
from labpilot.api.file_facts import FileFacts
from labpilot.ingest import Chunk
from labpilot.store import StoredChunk, StoreError

DEF = "[train.py · class Data · def pos_weight · lines 1-2]"
MAIN = "[train.py · def main · lines 3-4]"


def stored(index, header, text):
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=header,
        source="train.py",
        start_line=1,
        end_line=2,
    )


def chunk(header):
    return Chunk(
        text="x",
        source="train.py",
        start_line=1,
        end_line=2,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
        header=header,
    )


def test_facts_name_only_the_unused_functions_these_parts_define(monkeypatch):
    reads = []

    def fake_read(conn, artifact_id):
        reads.append(artifact_id)
        return (
            stored(0, DEF, "    def pos_weight(self):\n        return 1.7"),
            stored(1, MAIN, "def main():\n    run()\n    main_loop()"),
        )

    monkeypatch.setattr(file_facts, "read_chunks", fake_read)
    facts = FileFacts("conn")

    text = facts.facts_for([chunk(DEF)])

    assert text == (
        f"`pos_weight` (defined in {DEF}) is never called or named anywhere else "
        "in this file."
    )
    assert (
        facts.facts_for([chunk(MAIN)])
        == f"`main` (defined in {MAIN}) is never called or named anywhere else "
        "in this file."
    )
    assert reads == ["B-1"]


def test_the_file_is_read_once_even_by_many_checks_at_once(monkeypatch):
    reads = []

    def fake_read(conn, artifact_id):
        reads.append(artifact_id)
        return (stored(0, DEF, "def pos_weight(self):"),)

    monkeypatch.setattr(file_facts, "read_chunks", fake_read)
    facts = FileFacts("conn")
    threads = [
        threading.Thread(target=facts.facts_for, args=([chunk(DEF)],)) for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert reads == ["B-1"]


def test_a_store_error_gives_no_facts_and_no_crash(monkeypatch):
    def broken(conn, artifact_id):
        raise StoreError("down")

    monkeypatch.setattr(file_facts, "read_chunks", broken)

    assert FileFacts("conn").facts_for([chunk(DEF)]) == ""


def test_the_outline_is_built_from_the_headers_once(monkeypatch):
    reads = []

    def fake_headers(conn, artifact_id, *, opening_chars):
        reads.append(artifact_id)
        return ()

    monkeypatch.setattr(file_facts, "read_headers", fake_headers)
    monkeypatch.setattr(file_facts, "build_map", lambda parts, budget: "the map")
    facts = FileFacts("conn")

    assert facts.outline("B-1") == "the map"
    assert facts.outline("B-1") == "the map"
    assert reads == ["B-1"]
