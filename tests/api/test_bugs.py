import threading

import pytest

from labpilot.agent import (
    BUGS_TOOL_NAME,
    CHECKLIST_AUDIT_TOOL_NAME,
    CHECKLIST_TOOL_NAME,
    SKEPTIC_TOOL_NAME,
    Bug,
    BugsError,
)
from labpilot.api import file_parts
from labpilot.api.bugs import make_bug_finder
from labpilot.api.checkpoints import SAVED_TYPES
from labpilot.api.finding_lines import prior_text
from labpilot.api.prompting import build_answer_prompt
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import BUGS_SCAN_TOKENS, SKEPTIC_TOKENS, SKEPTIC_VOTES
from labpilot.prompts.bugs import CONCEPT, METHOD, TRACE
from labpilot.prompts.checklists import CHECKLIST_AUDIT as AUDIT
from labpilot.prompts.checklists import PITFALLS, STANDARDS
from labpilot.store import StoredChunk


def part(index, text, source="train.py"):
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=f"[{source} · part {index}]",
        source=source,
        start_line=index,
        end_line=index,
    )


def no_rules(prompt):
    return {"obligations": ["Is the secret at least 16 bytes long?"]}


def all_met(prompt):
    return {"answers": [{"n": 0, "meets": "yes"}]}


class FakeClient:
    """Answers each question by its tool: the hunts, the checklists, the audit and
    the skeptic."""

    def __init__(self, hunts, votes=None, rules=no_rules, audit=all_met):
        self.answers = {
            BUGS_TOOL_NAME: hunts,
            SKEPTIC_TOOL_NAME: votes,
            CHECKLIST_TOOL_NAME: rules,
            CHECKLIST_AUDIT_TOOL_NAME: audit,
        }
        self.prompts = []
        self.lock = threading.Lock()

    def generate(self, prompt, *, max_tokens, tool=None, problem_with=None):
        with self.lock:
            self.prompts.append((tool.name, prompt))
        answer = self.answers[tool.name](prompt)
        if isinstance(answer, Exception):
            raise answer
        return LLMResult(text="{}", model="fake", tier=1, arguments=answer)


def one_defect(prompt):
    if TRACE.header in prompt and "beta1**step" in prompt:
        return {
            "defects": [
                {
                    "kind": "logic",
                    "part": 0,
                    "quote": "beta1**step",
                    "text": "the second moment uses beta1",
                }
            ]
        }
    return {"defects": []}


def says(*verdicts):
    def answer(prompt):
        return {"verdicts": [{"n": 0, "verdict": v, "reason": v} for v in verdicts]}

    return answer


def finder(monkeypatch, client, parts, skeptic=None, trace=None):
    monkeypatch.setattr(file_parts, "read_chunks", lambda conn, artifact_id: parts)
    return make_bug_finder(
        "conn",
        client=client,
        skeptic_client=skeptic or client,
        trace_client=trace or client,
    )


PARTS = (part(0, "bias2 = 1 - beta1**step"),)


def test_the_three_questions_are_asked_and_two_read_the_summary(monkeypatch):
    client = FakeClient(lambda p: {"defects": []})

    finder(monkeypatch, client, PARTS)("B-1", "an optimiser")

    asked = {
        head.name: p
        for _, p in client.prompts
        for head in (TRACE, METHOD, CONCEPT, STANDARDS, PITFALLS, AUDIT)
        if head.header in p
    }
    assert set(asked) == {
        "bugs-trace",
        "bugs-method",
        "bugs-concept",
        "bugs-standards",
        "bugs-pitfalls",
        "bugs-audit",
    }
    assert (
        "an optimiser" in asked["bugs-trace"]
        and "an optimiser" in asked["bugs-concept"]
    )
    assert "an optimiser" not in asked["bugs-method"]


def test_a_suspect_with_one_real_vote_is_kept_and_labelled(monkeypatch):
    client = FakeClient(one_defect, says("real"))

    (got,) = finder(monkeypatch, client, PARTS)("B-1", "")

    assert got.verdict == "real" and got.evidence.side == "B"
    asked = [name for name, _ in client.prompts if name == SKEPTIC_TOOL_NAME]
    assert len(asked) == SKEPTIC_VOTES == 2


def test_a_suspect_every_vote_throws_out_is_not_reported(monkeypatch):
    client = FakeClient(one_defect, says("false"))

    assert finder(monkeypatch, client, PARTS)("B-1", "") == ()


def test_when_the_skeptic_fails_the_suspect_is_shown_unchecked(monkeypatch):
    client = FakeClient(one_defect, lambda p: AllFreeTiersExhausted(()))

    (got,) = finder(monkeypatch, client, PARTS)("B-1", "")

    assert got.verdict == "unchecked"


def test_the_skeptic_reads_the_whole_file_when_it_is_small(monkeypatch):
    client = FakeClient(one_defect, says("real"))
    parts = (*PARTS, part(1, "other_code = 2"))

    finder(monkeypatch, client, parts)("B-1", "")

    skeptic = [p for name, p in client.prompts if name == SKEPTIC_TOOL_NAME][0]
    assert "other_code = 2" in skeptic


def test_on_a_big_file_the_skeptic_reads_only_the_suspects_parts(monkeypatch):
    client = FakeClient(one_defect, says("real"))
    filler = "x = 1\n" * (SKEPTIC_TOKENS // 4)
    parts = (*PARTS, part(1, "other_code = 2 " + filler), part(2, filler))

    finder(monkeypatch, client, parts)("B-1", "")

    skeptic = [p for name, p in client.prompts if name == SKEPTIC_TOOL_NAME][0]
    assert "beta1**step" in skeptic and "other_code = 2" not in skeptic


def test_the_calls_are_made_at_the_same_time(monkeypatch):
    # A small file: one trace, one method and one concept call, all at once.
    barrier = threading.Barrier(3, timeout=5)

    def hunts(prompt):
        barrier.wait()
        return {"defects": []}

    finder(monkeypatch, FakeClient(hunts), PARTS)("B-1", "")


def test_the_two_checklists_are_written_at_the_same_time(monkeypatch):
    barrier = threading.Barrier(2, timeout=5)

    def rules(prompt):
        barrier.wait()
        return no_rules(prompt)

    finder(monkeypatch, FakeClient(lambda p: {"defects": []}, rules=rules), PARTS)(
        "B-1", ""
    )


SECRET = (part(0, "secretSize: 10,"),)


def breaks_rule(prompt):
    return {
        "answers": [
            {
                "n": 0,
                "meets": "no",
                "part": 0,
                "quote": "secretSize: 10,",
                "text": "the default secret is 80 bits",
            }
        ]
    }


def test_the_checklists_read_the_summary_and_the_headers_and_the_audit_the_code(
    monkeypatch,
):
    client = FakeClient(lambda p: {"defects": []}, says("real"), audit=breaks_rule)

    finder(monkeypatch, client, SECRET)("B-1", "a one-time password library")

    lists = [p for name, p in client.prompts if name == CHECKLIST_TOOL_NAME]
    assert {STANDARDS.header in p for p in lists} == {True, False}
    assert {PITFALLS.header in p for p in lists} == {True, False}
    for asked in lists:
        assert "a one-time password library" in asked
        assert "[train.py · part 0]" in asked and "secretSize: 10," not in asked
    (audit,) = [p for name, p in client.prompts if name == CHECKLIST_AUDIT_TOOL_NAME]
    assert AUDIT.header in audit and "secretSize: 10," in audit
    assert "0. Is the secret at least 16 bytes long?" in audit


def test_a_rule_the_code_breaks_becomes_a_concept_suspect_the_skeptic_judges(
    monkeypatch,
):
    client = FakeClient(lambda p: {"defects": []}, says("real"), audit=breaks_rule)

    (got,) = finder(monkeypatch, client, SECRET)("B-1", "")

    assert got.kind == "concept" and got.verdict == "real"
    assert "[obligation: Is the secret at least 16 bytes long?]" in got.text
    skeptic = [p for name, p in client.prompts if name == SKEPTIC_TOOL_NAME][0]
    assert "the default secret is 80 bits" in skeptic


def test_a_broken_rule_the_skeptic_calls_intended_is_kept_as_unclear(monkeypatch):
    # 2026-11-01: the skeptic called a 10-byte secret, MD5 and replay "intended".
    client = FakeClient(lambda p: {"defects": []}, says("intended"), audit=breaks_rule)

    (got,) = finder(monkeypatch, client, SECRET)("B-1", "")

    assert got.verdict == "unclear"


def test_when_no_checklist_is_written_there_is_no_audit(monkeypatch):
    client = FakeClient(
        lambda p: {"defects": []}, rules=lambda p: AllFreeTiersExhausted(())
    )

    assert finder(monkeypatch, client, PARTS)("B-1", "") == ()
    assert CHECKLIST_AUDIT_TOOL_NAME not in {name for name, _ in client.prompts}


def test_only_the_first_parts_up_to_the_scan_budget_are_hunted(monkeypatch, caplog):
    client = FakeClient(lambda p: {"defects": []})
    size = BUGS_SCAN_TOKENS // 4
    parts = tuple(part(n, "y" * (3 * size - 40)) for n in range(6))

    finder(monkeypatch, client, parts)("B-1", "")

    shown = "".join(p for _, p in client.prompts)
    assert "[train.py · part 3]" in shown and "[train.py · part 4]" not in shown
    assert "4 of 6 parts" in caplog.text


def test_the_trace_question_goes_to_the_trace_chain_and_no_other(monkeypatch):
    client = FakeClient(lambda p: {"defects": []}, votes=says("real"))
    trace = FakeClient(one_defect)

    found = finder(monkeypatch, client, PARTS, trace=trace)("B-1", "")

    assert [b.kind for b in found] == ["logic"]
    assert all(TRACE.header in p for _, p in trace.prompts)
    assert not any(TRACE.header in p for _, p in client.prompts)
    assert any(METHOD.header in p for _, p in client.prompts)


def test_a_file_that_does_not_fit_is_skipped_and_never_read_in_part(
    monkeypatch, caplog
):
    client = FakeClient(lambda p: {"defects": []})
    third = BUGS_SCAN_TOKENS // 3
    parts = (
        part(0, "a" * (3 * third), "a.py"),
        part(1, "b" * (3 * third), "b.py"),
        part(2, "b" * (3 * third), "b.py"),
        part(3, "c" * 300, "c.py"),
    )

    finder(monkeypatch, client, parts)("B-1", "")

    shown = "".join(p for _, p in client.prompts)
    assert "[a.py · part 0]" in shown and "[c.py · part 3]" in shown
    assert "b.py" not in shown
    assert "2 of 4 parts, 2 of 3 files" in caplog.text


def test_the_big_groups_never_split_a_small_file(monkeypatch):
    client = FakeClient(lambda p: {"defects": []})
    each = BUGS_SCAN_TOKENS // 30
    parts = tuple(part(n, "z" * (3 * each - 40), f"f{n // 4}.py") for n in range(30))

    finder(monkeypatch, client, parts)("B-1", "")

    for head in (METHOD, CONCEPT, AUDIT):
        asked = [p for _, p in client.prompts if head.header in p]
        assert len(asked) == 2, head.name
        for n in range(8):
            holding = [p for p in asked if f"[f{n}.py · part" in p]
            assert len(holding) == 1, (head.name, n)


def test_when_every_question_fails_the_error_says_so(monkeypatch):
    def fail(prompt):
        return AllFreeTiersExhausted(())

    client = FakeClient(fail, rules=fail, audit=fail)

    with pytest.raises(BugsError, match="no tier"):
        finder(monkeypatch, client, PARTS)("B-1", "")


def test_a_dropped_connection_stops_the_hunt_and_not_the_answer(monkeypatch):
    import psycopg

    def dead(conn, artifact_id):
        raise psycopg.OperationalError("server closed the connection unexpectedly")

    monkeypatch.setattr(file_parts, "read_chunks", dead)
    client = FakeClient(one_defect)
    find = make_bug_finder(
        "conn", client=client, skeptic_client=client, trace_client=client
    )

    with pytest.raises(BugsError, match="could not read B-1"):
        find("B-1", "")


def test_a_bug_survives_the_chat_save():
    assert Bug in SAVED_TYPES


def chunk():
    return Chunk(
        text="bias2 = 1 - beta1**step",
        source="adam.py",
        start_line=1,
        end_line=1,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
    )


def test_the_bugs_are_written_in_the_answer_prompt():
    found = Bug(
        "logic", "beta1 is used", "[adam.py · part 0]", "beta1**step", "high", "real"
    )

    prompt, _ = build_answer_prompt(
        (chunk(),), question="bugs?", files=1, bugs=(found,)
    )

    assert '[real - logic] beta1 is used ([adam.py · part 0]): "beta1**step".' in prompt
    assert "The file was also read alone" in prompt


def test_a_real_high_bug_is_kept_before_the_unclear_ones():
    real = Bug("logic", "the real one", "[t]", "q", "high", "real")
    unclear = [
        Bug("code", f"maybe {n} " * 5, "[t]", "q", "high", "unclear") for n in range(40)
    ]

    text = prior_text([], [*unclear, real], 400)

    assert "[real - logic] the real one" in text
    assert "left out for room" in text


def syntax_claim(prompt):
    if TRACE.header in prompt:
        return {
            "defects": [
                {
                    "kind": "code",
                    "part": 0,
                    "quote": "else:",
                    "text": "two else blocks for one if: a syntax error",
                }
            ]
        }
    return {"defects": []}


def test_a_syntax_claim_on_python_that_parses_never_reaches_the_answer(monkeypatch):
    # 2026-11-02: two "else" at different indents (a nested if) were judged a
    # real syntax error in all three runs.
    nested = (
        "if a:\n    if b:\n        x = 1\n    else:\n        x = 2\nelse:\n    x = 3\n"
    )
    client = FakeClient(syntax_claim, says("real"))

    got = finder(monkeypatch, client, (part(0, nested),))("B-1", "")

    assert got == ()
    assert SKEPTIC_TOOL_NAME not in {name for name, _ in client.prompts}


# The Go text is also valid Python, so only the ".py" rule keeps that claim.
@pytest.mark.parametrize(
    "source,text", [("t.py", "else:\n  x = (\n"), ("t.go", "x = {'else:': 1}\n")]
)
def test_a_syntax_claim_the_parser_cannot_disprove_is_kept(monkeypatch, source, text):
    client = FakeClient(syntax_claim, says("real"))

    (got,) = finder(monkeypatch, client, (part(0, text, source),))("B-1", "")

    assert got.verdict == "real"
