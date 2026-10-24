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


CONFIG = "[train.py · class TrainConfig · lines 1-9]"
LOOP = "[train.py · class Trainer · def step · lines 50-60]"


def loop_chunk():
    return Chunk(
        text="clip(params, self.config.CLIP_NORM)",
        source="train.py",
        start_line=50,
        end_line=60,
        side="B",
        artifact_id="B-1",
        chunk_index=7,
        header=LOOP,
    )


def test_expand_adds_the_part_that_sets_a_constant_the_parts_only_use(monkeypatch):
    stored_parts = (
        stored(0, CONFIG, "class TrainConfig:\n    CLIP_NORM = 1.5"),
        stored(7, LOOP, "clip(params, self.config.CLIP_NORM)"),
    )
    monkeypatch.setattr(file_facts, "read_chunks", lambda conn, a: stored_parts)

    got = FileFacts("conn").expand((loop_chunk(),))

    assert [c.chunk_index for c in got] == [7, 0]
    assert got[1].header == CONFIG and got[1].side == "B"


def test_expand_adds_nothing_when_the_parts_already_set_it(monkeypatch):
    here = Chunk(
        text="CLIP_NORM = 1.5\nclip(p, CLIP_NORM)",
        source="train.py",
        start_line=1,
        end_line=2,
        side="B",
        artifact_id="B-1",
        chunk_index=3,
        header="[train.py · lines 1-2]",
    )
    monkeypatch.setattr(
        file_facts,
        "read_chunks",
        lambda conn, a: (
            stored(0, CONFIG, "CLIP_NORM = 9"),
            stored(3, "[train.py · lines 1-2]", here.text),
        ),
    )

    assert FileFacts("conn").expand((here,)) == (here,)


def test_expand_adds_at_most_a_few_parts(monkeypatch):
    names = [f"NAME_{n}" for n in range(6)]
    stored_parts = tuple(
        stored(n, f"[cfg · {n}]", f"{name} = {n}") for n, name in enumerate(names)
    ) + (stored(99, LOOP, " ".join(f"cfg.{name}" for name in names)),)
    monkeypatch.setattr(file_facts, "read_chunks", lambda conn, a: stored_parts)
    used = Chunk(
        text=stored_parts[-1].text,
        source="train.py",
        start_line=1,
        end_line=2,
        side="B",
        artifact_id="B-1",
        chunk_index=99,
        header=LOOP,
    )

    got = FileFacts("conn").expand((used,))

    assert len(got) == 1 + file_facts.MAX_DEFINITIONS


def test_the_checker_reads_the_expanded_parts(monkeypatch):
    from labpilot.agent import Claim
    from labpilot.api.checking import make_checker
    from labpilot.llm import LLMResult

    prompts = []

    class Client:
        def generate(self, prompt, *, max_tokens, tool=None, problem_with=None):
            prompts.append(prompt)
            return LLMResult(
                text="{}",
                model="m",
                tier=1,
                arguments={
                    "verdict": "mismatch",
                    "kind": "choice",
                    "part": 1,
                    "quote": "CLIP_NORM = 1.5",
                    "note": "1.5 not 1.0",
                },
            )

    extra = Chunk(
        text="CLIP_NORM = 1.5",
        source="train.py",
        start_line=1,
        end_line=1,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
        header=CONFIG,
    )
    check = make_checker(Client(), None, lambda chunks: (*chunks, extra))

    finding = check(Claim("clip at 1.0", "[p]", "clip"), (loop_chunk(),))

    assert "CLIP_NORM = 1.5" in prompts[0]
    assert finding.verdict == "mismatch" and finding.evidence is extra


def test_a_dead_connection_gives_no_help_and_no_crash(monkeypatch):
    import psycopg

    def dead(conn, artifact_id):
        raise psycopg.OperationalError("SSL SYSCALL error: connection abort")

    monkeypatch.setattr(file_facts, "read_chunks", dead)
    monkeypatch.setattr(file_facts, "read_headers", lambda *a, **k: dead(*a))
    facts = FileFacts("conn")

    assert facts.facts_for([chunk(DEF)]) == ""
    assert facts.expand([chunk(DEF)]) == (chunk(DEF),)
    assert facts.outline("B-1") == ""
