import threading

import pytest

from labpilot.agent import A_SILENT, CodeFinding, DifferencesError
from labpilot.api import asking, differences
from labpilot.api.differences import make_difference_finder
from labpilot.api.prompting import build_answer_prompt, code_findings_text
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import A_WHOLE_TOKENS, SCAN_TOKENS
from labpilot.store import StoredChunk


def stored(index, text, header, source, start, end):
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=header,
        source=source,
        start_line=start,
        end_line=end,
    )


A_PARTS = (
    stored(
        0,
        "The mask excludes padding and nothing else.",
        "[paper.md · 4]",
        "paper.md",
        1,
        2,
    ),
)


def b_part(index, text, header=None):
    return stored(
        index, text, header or f"[train.py · part {index}]", "train.py", index, index
    )


class Facts:
    def __init__(self, unused=None):
        self._unused = unused or {}

    def unused(self, artifact_id):
        return self._unused


class FakeClient:
    def __init__(self, answers):
        self.answers = answers
        self.prompts = []
        self.lock = threading.Lock()

    def generate(self, prompt, *, max_tokens, tool=None, problem_with=None):
        with self.lock:
            self.prompts.append(prompt)
        arguments = self.answers(prompt)
        if isinstance(arguments, Exception):
            raise arguments
        return LLMResult(text="{}", model="fake", tier=1, arguments=arguments)


def mask_answer(prompt):
    if "stop_mask" in prompt:
        return {
            "items": [
                {
                    "text": "B masks stopwords",
                    "part": 0,
                    "quote": "mask * stop_mask",
                    "a_says": "nothing else",
                }
            ]
        }
    return {"items": []}


def finder(monkeypatch, client, b_parts, *, a_parts=A_PARTS, unused=None):
    def fake_read(conn, artifact_id):
        return a_parts if artifact_id.startswith("A") else b_parts

    monkeypatch.setattr(differences, "read_chunks", fake_read)
    return make_difference_finder("conn", client, Facts(unused))


def test_each_group_of_b_is_read_beside_the_whole_of_a(monkeypatch):
    client = FakeClient(mask_answer)
    parts = (b_part(0, "mask = mask * stop_mask"),)

    got = finder(monkeypatch, client, parts)("A-1", "B-1")

    assert got[0].text == "B masks stopwords"
    assert got[0].evidence.chunk_index == 0 and got[0].evidence.side == "B"
    assert "FILE A, WHOLE" in client.prompts[0]
    assert "The mask excludes padding and nothing else." in client.prompts[0]


def test_a_big_b_is_read_in_groups_at_the_same_time(monkeypatch):
    barrier = threading.Barrier(2, timeout=5)

    def answers(prompt):
        barrier.wait()
        return {"items": []}

    parts = tuple(b_part(n, "x" * 1500) for n in range(8))  # ~4,000 tokens

    finder(monkeypatch, FakeClient(answers), parts)("A-1", "B-1")


def test_a_reference_too_big_to_put_beside_b_is_refused_before_any_call(monkeypatch):
    client = FakeClient(mask_answer)
    big_a = (stored(0, "x" * (3 * A_WHOLE_TOKENS + 3), "[a]", "a.md", 1, 2),)

    with pytest.raises(DifferencesError, match="too big"):
        finder(monkeypatch, client, (b_part(0, "x"),), a_parts=big_a)("A-1", "B-1")
    assert client.prompts == []


def test_only_the_first_parts_up_to_the_scan_budget_are_read(monkeypatch, caplog):
    client = FakeClient(lambda prompt: {"items": []})
    size = SCAN_TOKENS // 4
    parts = tuple(b_part(n, "y" * (3 * size - 40)) for n in range(6))

    finder(monkeypatch, client, parts)("A-1", "B-1")

    shown = "".join(client.prompts)
    assert "[train.py · part 3]" in shown and "[train.py · part 4]" not in shown
    assert "4 of 6 parts" in caplog.text


def test_when_every_group_fails_the_error_says_so(monkeypatch):
    client = FakeClient(lambda prompt: AllFreeTiersExhausted(()))

    with pytest.raises(DifferencesError, match="no tier"):
        finder(monkeypatch, client, (b_part(0, "x"),))("A-1", "B-1")


def test_a_function_never_named_again_is_added_with_its_def_line(monkeypatch):
    header = "[train.py · class Data · def pos_weight · lines 5-6]"
    parts = (b_part(0, "    def pos_weight(self):\n        return 1.7", header),)

    got = finder(
        monkeypatch,
        FakeClient(lambda p: {"items": []}),
        parts,
        unused={"pos_weight": header},
    )("A-1", "B-1")

    (unused,) = got
    assert "`pos_weight` is defined in B and never called" in unused.text
    assert unused.quote == "def pos_weight(self):"
    assert unused.a_says == A_SILENT and unused.evidence.header == header


def test_the_code_findings_are_written_in_the_answer_prompt():
    chunk = Chunk(
        text="mask = mask * stop_mask",
        source="train.py",
        start_line=1,
        end_line=1,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
    )
    items = (
        CodeFinding(
            "B masks stopwords", "[train.py · part 0]", "stop_mask", "nothing else"
        ),
        CodeFinding(
            "B adds a cosine feature", "[train.py · part 9]", "cosine", A_SILENT
        ),
    )

    prompt, _ = build_answer_prompt(
        (chunk,), question="why?", files=2, code_findings=items
    )

    assert (
        '[B differs] B masks stopwords B ([train.py · part 0]): "stop_mask".' in prompt
    )
    assert 'A says: "nothing else"' in prompt
    assert "[A silent] B adds a cosine feature" in prompt
    assert code_findings_text(()) == ""


def test_ask_hands_the_graph_the_scan_of_b(monkeypatch):
    seen = {}
    monkeypatch.setattr(asking, "build_graph", lambda **kw: seen.update(kw))
    monkeypatch.setattr(
        asking, "make_difference_finder", lambda conn, client, facts: ("find", conn)
    )

    asking._ask_graph("conn", "client")

    assert seen["find_missing"] == ("find", "conn")


def test_on_the_search_path_the_deciding_parts_go_first_and_survive_the_cut():
    def part(index):
        return Chunk(
            text="z " * 1200,
            source="train.py",
            start_line=index,
            end_line=index,
            side="B",
            artifact_id="B-1",
            chunk_index=index,
        )

    searched = tuple(part(n) for n in range(40))
    deciding = part(77)

    _, picked = build_answer_prompt(
        searched, question="why?", files=2, totals={"B": 100}, evidence=(deciding,)
    )

    assert picked[0] == deciding
    assert len(picked) < 41


def test_when_everything_was_read_the_evidence_changes_nothing():
    small = (
        Chunk(
            text="a",
            source="t.py",
            start_line=1,
            end_line=1,
            side="B",
            artifact_id="B-1",
            chunk_index=0,
        ),
    )
    extra = Chunk(
        text="b",
        source="t.py",
        start_line=2,
        end_line=2,
        side="B",
        artifact_id="B-1",
        chunk_index=5,
    )

    _, picked = build_answer_prompt(
        small, question="why?", files=2, totals=None, evidence=(extra,)
    )

    assert picked == small


def test_the_reference_is_read_whole_only_when_small(monkeypatch):
    from types import SimpleNamespace

    from labpilot.prompts import A_WHOLE_TOKENS

    seen = {}
    monkeypatch.setattr(asking, "build_graph", lambda **kw: seen.update(kw))
    monkeypatch.setattr(asking, "stuffed_chunks", lambda conn, sides: ("all of", sides))
    asking._ask_graph("conn", "client")
    whole = seen["whole_side"]
    small = SimpleNamespace(characters=3 * A_WHOLE_TOKENS)
    big = SimpleNamespace(characters=3 * A_WHOLE_TOKENS + 3)

    assert whole({"A": small}, "A") == ("all of", {"A": small})
    assert whole({"A": big}, "A") is None
    assert whole({"B": small}, "B") is None


def many_findings():
    from labpilot.agent import Claim, Finding

    claim = Claim("a long claim about the setting " * 3, "[paper.md]", "q")
    checks = [Finding(claim, "match", "", "[s]", "quote", "same") for _ in range(60)]
    checks.append(Finding(claim, "mismatch", "choice", "[s]", "dt = 0.05", "bigger"))
    codes = [
        CodeFinding("B does a thing that A never says " * 2, "[t]", "x", A_SILENT)
        for _ in range(60)
    ]
    codes.append(CodeFinding("B masks stopwords", "[t]", "stop_mask", "nothing else"))
    return checks, codes


def test_many_findings_never_crowd_the_evidence_out_of_the_prompt():
    # 2026-10-25: 48 check lines and 33 code lines made the fixed text bigger
    # than a 12,000-token budget, and the answer was refused.
    from labpilot.api import prompting

    checks, codes = many_findings()
    part = Chunk(
        text="x = 1",
        source="t.py",
        start_line=1,
        end_line=1,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
    )
    old = prompting.PROMPT_BUDGET
    prompting.PROMPT_BUDGET = 12_000
    try:
        prompt, picked = build_answer_prompt(
            (part,),
            question="why?",
            files=2,
            totals={"B": 9},
            findings=checks,
            code_findings=codes,
        )
    finally:
        prompting.PROMPT_BUDGET = old

    assert picked == (part,)
    assert "more lines of findings were left out for room" in prompt


def test_the_most_telling_findings_are_kept_first():
    from labpilot.api.prompting import prior_text

    checks, codes = many_findings()

    text = prior_text(checks, codes, 600)

    assert "[mismatch - choice]" in text
    assert "[B differs] B masks stopwords" in text
    assert "\n[match]" not in text
    assert "left out for room" in text


def test_a_match_is_written_short():
    from labpilot.agent import Claim, Finding
    from labpilot.api.prompting import prior_text

    match = Finding(
        Claim("the batch is 128", "[p]", "q"),
        "match",
        "",
        "[s]",
        "BATCH = 128",
        "the same",
    )

    text = prior_text([match], [], 10_000)

    assert '[match] A says "the batch is 128"' in text
    assert "BATCH = 128" not in text


def test_every_id_the_prompt_shows_names_the_same_part_in_the_saved_list():
    # 2026-10-24: the deciding parts were put in FRONT before the ids were
    # numbered, while the page resolved the ids on the old list, so only 8 of
    # 19 citations resolved.
    import re

    from labpilot.agent import Claim, Finding
    from labpilot.agent.respond import make_respond_node
    from labpilot.prompts import resolve

    def part(index):
        return Chunk(
            text=f"value_{index} = {index}\n" + "z " * 1200,
            source="train.py",
            start_line=index,
            end_line=index,
            side="B",
            artifact_id="B-1",
            chunk_index=index,
        )

    searched = tuple(part(n) for n in range(40))
    claim = Claim("x", "[paper.md]", "x")
    findings = [
        Finding(claim, "mismatch", "choice", "[s]", "q", "n", part(77)),
        Finding(claim, "mismatch", "choice", "[s]", "q", "n", part(30)),
    ]
    node = make_respond_node(build_answer_prompt, lambda prompt: prompt)

    out = node(
        {
            "chunks": searched,
            "question": "why?",
            "totals": {"B": 100},
            "a": "",
            "b": "B-1",
            "findings": findings,
        }
    )

    shown = re.findall(r"^(B-\d+)  .*\n(value_\d+ = \d+)$", out["prompt"], re.M)
    assert "value_77 = 77" in {text for _, text in shown}
    assert len(shown) == len(out["selected"])
    for name, text in shown:
        assert resolve(name, text, out["chunks"]), name


def test_a_dropped_connection_stops_the_scan_and_not_the_answer(monkeypatch):
    import psycopg

    def dead(conn, artifact_id):
        raise psycopg.OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(differences, "read_chunks", dead)
    find = make_difference_finder("conn", FakeClient(mask_answer), Facts())

    with pytest.raises(DifferencesError, match="could not read the files"):
        find("A-1", "B-1")


def stuffed_pair(parts=60):
    return tuple(
        Chunk(
            text=f"line_{n} = {n}\n" + "q " * 600,
            source="t.py",
            start_line=n,
            end_line=n,
            side="B",
            artifact_id="B-1",
            chunk_index=n,
        )
        for n in range(parts)
    )


def test_when_everything_was_read_the_parts_come_before_the_finding_lines():
    # 2026-10-24: the findings of a stuffed run cut B from 82 parts to 65.
    checks, codes = many_findings()
    chunks = stuffed_pair(40)

    prompt, picked = build_answer_prompt(
        chunks,
        question="why?",
        files=2,
        totals=None,
        findings=checks,
        code_findings=codes,
    )

    assert picked == chunks
    assert "[mismatch - choice]" in prompt


def test_when_the_parts_fill_the_budget_no_part_is_cut_for_a_finding_line():
    from labpilot.api import prompting

    checks, codes = many_findings()
    chunks = stuffed_pair(60)
    bare, _ = build_answer_prompt(chunks, question="why?", files=2, totals=None)
    old = prompting.PROMPT_BUDGET
    prompting.PROMPT_BUDGET = prompting.estimate_tokens(bare) + 50
    try:
        prompt, picked = build_answer_prompt(
            chunks,
            question="why?",
            files=2,
            totals=None,
            findings=checks,
            code_findings=codes,
        )
    finally:
        prompting.PROMPT_BUDGET = old

    assert picked == chunks
    assert "[mismatch - choice]" not in prompt
