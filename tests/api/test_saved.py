"""D104: the claims, differences and bugs of some files, made once and reused."""

import logging

import psycopg
import pytest

from labpilot.agent import Bug, Claim, Correspondence, GateError, Plan, Query
from labpilot.api import saved as saved_module
from labpilot.api.checkpoints import SERDE
from labpilot.api.errors import GenerationUnavailable
from labpilot.api.saved import (
    SavedResults,
    bugs_key,
    claims_key,
    differences_key,
    gate_key,
    saved_bugs,
    saved_claims,
    saved_differences,
    saved_gate,
    saved_summary,
    summary_key,
    with_saved_steps,
)

BUG = Bug("logic", "the step is never updated", "[solver.py]", "t = 0")
VERDICT = Correspondence("NONE", "different things")
CLAIM = Claim("the time step is 0.01 s", "[paper.md]", "time step is 0.01 s")


class FakeStore:
    """The two store functions over a dict, with an optional failure."""

    def __init__(self, monkeypatch, *, fail_read=False, fail_write=False):
        self.rows: dict[str, tuple[str, bytes, tuple[str, ...]]] = {}
        self.fail_read = fail_read
        self.fail_write = fail_write

        def read(conn, key):
            if self.fail_read:
                raise psycopg.OperationalError("gone")
            row = self.rows.get(key)
            return None if row is None else (row[0], row[1])

        def write(conn, key, kind, payload, *, artifacts):
            if self.fail_write:
                raise psycopg.OperationalError("gone")
            self.rows[key] = (kind, payload, artifacts)

        monkeypatch.setattr(saved_module, "read_saved", read)
        monkeypatch.setattr(saved_module, "write_saved", write)

    def put(self, key, value, artifacts=("B-1",)):
        kind, payload = SERDE.dumps_typed(tuple(value))
        self.rows[key] = (kind, payload, artifacts)


def counting(value):
    calls = []

    def make(*args):
        calls.append(args)
        return value

    return make, calls


def test_a_result_is_made_once_saved_and_then_reused(monkeypatch):
    store = FakeStore(monkeypatch)
    find, calls = counting((BUG,))

    first = SavedResults("conn")
    assert saved_bugs(first, find)("B-1", "a solver") == (BUG,)
    second = SavedResults("conn")
    assert saved_bugs(second, find)("B-1", "a solver") == (BUG,)

    assert len(calls) == 1
    assert first.made == ["bugs"] and first.reused == []
    assert second.reused == ["bugs"] and second.made == []
    assert store.rows[bugs_key("B-1")][2] == ("B-1",)


def test_the_claims_are_saved_for_the_reference_alone(monkeypatch):
    store = FakeStore(monkeypatch)
    extract, calls = counting((CLAIM,))

    saved_claims(SavedResults("conn"), extract)("A-1")
    again = SavedResults("conn")
    assert saved_claims(again, extract)("A-1") == (CLAIM,)

    assert len(calls) == 1
    assert again.reused == ["claims"]
    assert store.rows[claims_key("A-1")][2] == ("A-1",)


def test_the_differences_are_saved_for_the_pair_and_its_facts(monkeypatch):
    store = FakeStore(monkeypatch)
    find, calls = counting(())

    saved_differences(SavedResults("conn"), find)("A-1", "B-1", ["fact one"])
    saved_differences(SavedResults("conn"), find)("A-1", "B-1", ["fact one"])
    saved_differences(SavedResults("conn"), find)("A-1", "B-1", ["fact two"])

    # The same facts are reused; other facts (a new claims run) are made again.
    assert len(calls) == 2
    assert store.rows[differences_key("A-1", "B-1", ["fact one"])][2] == ("A-1", "B-1")


def test_an_empty_result_is_saved_and_reused_too(monkeypatch):
    FakeStore(monkeypatch)
    find, calls = counting(())

    saved_bugs(SavedResults("conn"), find)("B-1", "")
    again = SavedResults("conn")
    assert saved_bugs(again, find)("B-1", "") == ()

    assert len(calls) == 1
    assert again.reused == ["bugs"]


def test_a_failed_step_is_not_saved(monkeypatch):
    store = FakeStore(monkeypatch)

    def broken(artifact, summary):
        raise RuntimeError("no tier")

    with pytest.raises(RuntimeError):
        saved_bugs(SavedResults("conn"), broken)("B-1", "")

    assert store.rows == {}


def test_a_database_that_cannot_be_read_makes_the_result_again(monkeypatch, caplog):
    store = FakeStore(monkeypatch, fail_read=True)
    store.put(bugs_key("B-1"), (BUG,))
    find, calls = counting(())

    with caplog.at_level(logging.WARNING):
        assert saved_bugs(SavedResults("conn"), find)("B-1", "") == ()

    assert len(calls) == 1
    assert "could not read the saved" in caplog.text


def test_a_database_that_cannot_be_written_still_gives_the_result(monkeypatch, caplog):
    FakeStore(monkeypatch, fail_write=True)
    find, _ = counting((BUG,))

    with caplog.at_level(logging.WARNING):
        assert saved_bugs(SavedResults("conn"), find)("B-1", "") == (BUG,)

    assert "could not save" in caplog.text


def test_a_new_instruction_version_never_reads_an_old_result(monkeypatch):
    old = bugs_key("B-1")
    monkeypatch.setattr(saved_module, "BUGS_VERSION", 999)

    assert bugs_key("B-1") != old


PLAN = Plan(steps=(), queries=(Query("B", "the step"),))


def planner(question, a, b):
    return PLAN


def test_a_saved_bug_hunt_is_always_planned_because_it_costs_nothing(monkeypatch):
    # "explain the second bug" may be planned with no step; the answer must
    # still see the saved bugs.
    store = FakeStore(monkeypatch)
    store.put(bugs_key("B-1"), (BUG,))

    plan = with_saved_steps(SavedResults("conn"), planner)("explain bug 2", "", "B-1")

    assert plan.steps == ("find_bugs",)
    assert plan.queries == PLAN.queries


def test_saved_differences_are_planned_only_with_their_saved_claims(monkeypatch):
    store = FakeStore(monkeypatch)
    store.put(claims_key("A-1"), (CLAIM,), ("A-1",))
    store.put(differences_key("A-1", "B-1", [CLAIM.text]), (), ("A-1", "B-1"))

    plan = with_saved_steps(SavedResults("conn"), planner)("why?", "A-1", "B-1")

    assert plan.steps == ("find_differences",)


def test_with_nothing_saved_the_plan_is_left_as_it_was(monkeypatch):
    FakeStore(monkeypatch)

    plan = with_saved_steps(SavedResults("conn"), planner)("why?", "A-1", "B-1")

    assert plan is PLAN


def test_the_reference_alone_is_never_given_a_saved_bug_hunt(monkeypatch):
    # D106: only B is hunted, so a saved hunt of A is never added for A alone.
    store = FakeStore(monkeypatch)
    store.put(bugs_key("A-1"), (BUG,), ("A-1",))

    plan = with_saved_steps(SavedResults("conn"), planner)("why?", "A-1", "")

    assert plan is PLAN


def test_a_summary_is_made_once_and_read_again(monkeypatch):
    FakeStore(monkeypatch)
    make, calls = counting("a short summary")
    summary = saved_summary(SavedResults("conn"), make)

    assert summary("A-1") == "a short summary"
    assert summary("A-1") == "a short summary"
    assert calls == [("A-1",)]


def test_a_summary_is_tied_to_its_file_and_to_no_other(monkeypatch):
    store = FakeStore(monkeypatch)
    make, calls = counting("a short summary")
    summary = saved_summary(SavedResults("conn"), make)

    summary("A-1")
    summary("B-2")

    assert calls == [("A-1",), ("B-2",)]
    assert store.rows[summary_key("A-1")][2] == ("A-1",)
    assert store.rows[summary_key("B-2")][2] == ("B-2",)


def test_a_summary_that_cannot_be_made_is_not_saved(monkeypatch):
    store = FakeStore(monkeypatch)

    def fails(artifact):
        raise GenerationUnavailable("every free tier failed", attempts=())

    with pytest.raises(GenerationUnavailable):
        saved_summary(SavedResults("conn"), fails)("A-1")

    assert store.rows == {}


def test_a_new_instruction_version_makes_the_summary_again(monkeypatch):
    FakeStore(monkeypatch)
    make, calls = counting("a short summary")
    summary = saved_summary(SavedResults("conn"), make)

    summary("A-1")
    monkeypatch.setattr(saved_module, "SUMMARY_VERSION", 2)
    summary("A-1")

    assert len(calls) == 2


def test_a_summary_is_not_listed_as_analysis(monkeypatch):
    FakeStore(monkeypatch)
    saved = SavedResults("conn")
    summary = saved_summary(saved, counting("a short summary")[0])

    summary("A-1")
    summary("A-1")

    assert saved.reused == []
    assert saved.made == []


def test_a_step_that_is_not_a_summary_is_listed_as_analysis(monkeypatch):
    FakeStore(monkeypatch)
    saved = SavedResults("conn")
    claims = saved_claims(saved, counting((CLAIM,))[0])

    claims("A-1")
    claims("A-1")

    assert saved.made == ["claims"]
    assert saved.reused == ["claims"]


def test_a_database_that_fails_still_gives_the_summary(monkeypatch):
    FakeStore(monkeypatch, fail_read=True, fail_write=True)
    make, calls = counting("a short summary")
    summary = saved_summary(SavedResults("conn"), make)

    assert summary("A-1") == "a short summary"
    assert summary("A-1") == "a short summary"
    assert len(calls) == 2


def test_a_verdict_is_made_once_and_read_again(monkeypatch):
    FakeStore(monkeypatch)
    make, calls = counting(VERDICT)
    gate = saved_gate(SavedResults("conn"), make)

    assert gate("A-1", "B-1", "about memory", "about images") == VERDICT
    assert gate("A-1", "B-1", "about memory", "about images") == VERDICT
    assert calls == [("about memory", "about images")]


def test_a_verdict_comes_back_as_a_correspondence_and_not_as_a_dict(monkeypatch):
    FakeStore(monkeypatch)
    gate = saved_gate(SavedResults("conn"), counting(VERDICT)[0])

    gate("A-1", "B-1", "about memory", "about images")
    again = saved_gate(SavedResults("conn"), counting(VERDICT)[0])

    assert isinstance(
        again("A-1", "B-1", "about memory", "about images"), Correspondence
    )


def test_a_verdict_is_tied_to_both_files(monkeypatch):
    store = FakeStore(monkeypatch)
    gate = saved_gate(SavedResults("conn"), counting(VERDICT)[0])

    gate("A-1", "B-1", "about memory", "about images")

    key = gate_key("A-1", "B-1", "about memory", "about images")
    assert store.rows[key][2] == ("A-1", "B-1")


def test_a_summary_written_again_in_other_words_gets_a_new_verdict(monkeypatch):
    FakeStore(monkeypatch)
    make, calls = counting(VERDICT)
    gate = saved_gate(SavedResults("conn"), make)

    gate("A-1", "B-1", "about memory", "about images")
    gate("A-1", "B-1", "about recall", "about images")

    assert len(calls) == 2


def test_the_same_two_texts_the_other_way_round_are_another_pair():
    assert gate_key("A-1", "B-1", "x", "y") != gate_key("A-1", "B-1", "y", "x")


def test_where_the_first_summary_ends_is_part_of_the_key():
    assert gate_key("A-1", "B-1", "ab", "c") != gate_key("A-1", "B-1", "a", "bc")


def test_a_gate_that_cannot_judge_is_not_saved(monkeypatch):
    store = FakeStore(monkeypatch)

    def cannot(summary_a, summary_b):
        raise GateError("no tier could judge it")

    with pytest.raises(GateError):
        saved_gate(SavedResults("conn"), cannot)("A-1", "B-1", "a", "b")

    assert store.rows == {}


def test_a_new_instruction_version_makes_the_verdict_again(monkeypatch):
    FakeStore(monkeypatch)
    make, calls = counting(VERDICT)
    gate = saved_gate(SavedResults("conn"), make)

    gate("A-1", "B-1", "a", "b")
    monkeypatch.setattr(saved_module, "GATE_VERSION", 2)
    gate("A-1", "B-1", "a", "b")

    assert len(calls) == 2


def test_a_verdict_is_not_listed_as_analysis(monkeypatch):
    FakeStore(monkeypatch)
    saved = SavedResults("conn")
    gate = saved_gate(saved, counting(VERDICT)[0])

    gate("A-1", "B-1", "a", "b")
    gate("A-1", "B-1", "a", "b")

    assert saved.reused == []
    assert saved.made == []


def test_a_database_that_fails_still_gives_the_verdict(monkeypatch):
    FakeStore(monkeypatch, fail_read=True, fail_write=True)
    make, calls = counting(VERDICT)
    gate = saved_gate(SavedResults("conn"), make)

    assert gate("A-1", "B-1", "a", "b") == VERDICT
    assert gate("A-1", "B-1", "a", "b") == VERDICT
    assert len(calls) == 2


def test_a_fast_hunt_never_answers_a_full_one(monkeypatch):
    FakeStore(monkeypatch)
    fast, _ = counting(())
    full, calls = counting((BUG,))

    saved_bugs(SavedResults("conn"), fast, fast=True)("B-1", "")

    assert saved_bugs(SavedResults("conn"), full)("B-1", "") == (BUG,)
    assert len(calls) == 1


def test_a_saved_full_hunt_answers_a_fast_question(monkeypatch):
    FakeStore(monkeypatch)
    saved_bugs(SavedResults("conn"), counting((BUG,))[0])("B-1", "")
    fast, calls = counting(())

    assert saved_bugs(SavedResults("conn"), fast, fast=True)("B-1", "") == (BUG,)
    assert calls == []


def test_a_saved_fast_hunt_is_planned_for_fast_questions_only(monkeypatch):
    store = FakeStore(monkeypatch)
    store.put(bugs_key("B-1", fast=True), (BUG,))

    def steps(fast):
        saved = SavedResults("conn")
        return with_saved_steps(saved, planner, fast=fast)("why?", "", "B-1").steps

    assert steps(True) == ("find_bugs",)
    assert steps(False) == ()
