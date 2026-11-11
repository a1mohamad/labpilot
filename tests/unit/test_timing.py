import ast
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMError, LLMResult, Tool
from labpilot.timing import (
    collecting,
    current_step,
    in_this_context,
    log_call,
    timed,
)


class Boom(Exception):
    pass


class FakeProvider:
    api_key_env = "KEY"

    def __init__(self, name, tier, outcome):
        self.name = name
        self.tier = tier
        self.outcome = outcome

    @property
    def pool(self):
        return f"{self.api_key_env}:{self.name}"

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return LLMResult(text=self.outcome, model=self.name, tier=self.tier)


def lines(collector, kind):
    return [r for r in collector.records if r["kind"] == kind]


# ---- the step clock ---------------------------------------------------------


def test_a_step_line_names_the_step_and_has_its_seconds():
    def slow(state):
        time.sleep(0.05)
        return {"plan": 1}

    with collecting() as collector:
        assert timed("plan", slow)({"q": 1}) == {"plan": 1}

    (line,) = lines(collector, "step")
    assert line["name"] == "plan"
    assert line["seconds"] >= 0.04
    # A start and end are clock times (about 1.7 billion), so compare the
    # distance between them, never the two numbers with a relative tolerance.
    assert line["end"] - line["start"] == pytest.approx(line["seconds"], abs=0.001)
    assert line["end"] - line["start"] >= 0.04


def test_a_step_that_fails_still_reports_and_the_error_goes_on():
    def broken(state):
        raise Boom("no")

    with collecting() as collector, pytest.raises(Boom):
        timed("measure", broken)({})

    assert [line["name"] for line in lines(collector, "step")] == ["measure"]
    assert current_step.get() == ""


def test_the_step_name_is_set_inside_the_node_and_gone_after_it():
    seen = []
    timed("gate", lambda state: seen.append(current_step.get()))({})

    assert seen == ["gate"]
    assert current_step.get() == ""


def test_two_steps_at_the_same_time_each_see_their_own_name():
    barrier = threading.Barrier(2, timeout=5)
    seen = {}

    def node(label):
        def run(state):
            barrier.wait()  # both are inside their step now
            seen[label] = current_step.get()

        return run

    threads = [
        threading.Thread(target=timed(label, node(label)), args=({},))
        for label in ("summarize_a", "summarize_b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen == {"summarize_a": "summarize_a", "summarize_b": "summarize_b"}


# ---- the call clock ---------------------------------------------------------


def test_a_call_line_has_the_step_the_tool_the_tier_and_the_failed_count():
    tool = Tool(name="make_plan", description="d", parameters={})
    client = LLMClient(
        chain=(
            FakeProvider("Dead", 1, LLMError("HTTP 400", status=400)),
            FakeProvider("Live", 2, "answer"),
        )
    )

    with collecting() as collector:
        timed("plan", lambda state: client.generate("hello", tool=tool))({})

    (call,) = lines(collector, "call")
    assert call["step"] == "plan"
    assert call["tool"] == "make_plan"
    assert (call["tier"], call["model"], call["failed"]) == (2, "Live", 1)
    assert call["seconds"] >= 0


def test_a_call_that_no_tier_answered_is_still_reported():
    client = LLMClient(chain=(FakeProvider("Dead", 1, LLMError("x", status=400)),))

    with collecting() as collector, pytest.raises(AllFreeTiersExhausted):
        timed("gate", lambda state: client.generate("hello"))({})

    (call,) = lines(collector, "call")
    assert call["step"] == "gate"
    assert call["tier"] is None
    assert call["model"] is None
    assert call["failed"] == 1


def test_a_call_outside_any_step_has_an_empty_step_name():
    with collecting() as collector:
        log_call(tool="", seconds=1.0, tier=3, model="m", failed=0)

    assert lines(collector, "call")[0]["step"] == ""


# ---- the label in other threads ---------------------------------------------


def test_a_thread_pool_job_loses_the_step_name_unless_it_is_carried():
    def lost(state):
        with ThreadPoolExecutor(1) as pool:
            return pool.submit(current_step.get).result()

    def carried(state):
        with ThreadPoolExecutor(1) as pool:
            return pool.submit(in_this_context(current_step.get)).result()

    assert timed("find_bugs", lost)({}) == ""  # why in_this_context exists
    assert timed("find_bugs", carried)({}) == "find_bugs"


def test_jobs_in_one_pool_can_share_one_captured_context():
    # One context can be entered by one thread at a time, so each run needs its
    # own copy. Two jobs inside the same moment would fail on a shared one.
    barrier = threading.Barrier(2, timeout=5)

    def job(_):
        barrier.wait()
        return current_step.get()

    def node(state):
        with ThreadPoolExecutor(2) as pool:
            return list(pool.map(in_this_context(job), [1, 2]))

    assert timed("find_differences", node)({}) == ["find_differences"] * 2


def test_the_collector_is_removed_when_the_block_ends():
    logger = logging.getLogger("labpilot.timing")
    before = (list(logger.handlers), logger.level)
    with collecting():
        assert len(logger.handlers) == len(before[0]) + 1
    assert (list(logger.handlers), logger.level) == before


# ---- a rule for every thread pool in the API ---------------------------------

API = Path(__file__).resolve().parents[2] / "labpilot" / "api"


def test_every_pool_job_in_the_api_carries_the_step_name():
    """A job given to a thread pool must go through in_this_context.

    The failure is quiet: a call from a pool thread still works, and only its
    line in the timing log would say step "".
    """
    found = 0
    for path in API.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"submit", "map"}
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pool"
            ):
                continue
            found += 1
            first = node.args[0]
            assert (
                isinstance(first, ast.Call)
                and isinstance(first.func, ast.Name)
                and first.func.id == "in_this_context"
            ), f"{path.name}:{node.lineno} gives a pool job without in_this_context"
    assert found >= 6, "the rule found too few pool jobs to be checking anything"
