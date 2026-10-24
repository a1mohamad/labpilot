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
