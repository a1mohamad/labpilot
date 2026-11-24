from labpilot.api import asking
from labpilot.llm import CHAIN, LLMClient, routes


def look_through_saved(monkeypatch):
    # The saved-results wrappers (D104) are tested in test_saved.py; here the
    # wiring is checked through them, so each wrapper hands back what it wraps.
    for name in ("saved_claims", "saved_differences", "saved_bugs", "with_saved_steps"):
        monkeypatch.setattr(asking, name, lambda saved, made: made)


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    def fake_differences(conn, *, audit, scan, judge_client, merge):
        seen["differences_clients"] = {
            "audit": audit,
            "scan": scan,
            "judge": judge_client,
        }
        return "find_differences"

    def fake_bugs(conn, **clients):
        seen["bug_clients"] = clients
        return "find_bugs"

    def fake_fresh(conn, *, statement, audit):
        seen["fresh_clients"] = {"fresh": statement, "audit": audit}
        return "fresh"

    look_through_saved(monkeypatch)
    monkeypatch.setattr(asking, "saved_fresh", lambda saved, made: made)
    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(asking, "make_planner", lambda conn, client: ("plan", client))
    monkeypatch.setattr(
        asking, "make_claims_extractor", lambda conn, client: ("extract", client)
    )
    monkeypatch.setattr(asking, "make_find_differences", fake_differences)
    monkeypatch.setattr(asking, "make_bug_finder", fake_bugs)
    monkeypatch.setattr(asking, "make_fresh_check", fake_fresh)
    return seen


def test_the_graph_gets_the_claims_the_differences_the_bugs_and_the_merge(
    monkeypatch,
):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert seen["extract_claims"] == ("extract", "client")
    assert seen["find_differences"] == "find_differences"
    assert seen["find_bugs"] == "find_bugs"
    assert callable(seen["final_merge"])


def route(task):
    return [p.name for p in routes.resolve(task, CHAIN)]


def step_clients(seen):
    """Every finder step and the client it was given, by the task it serves."""
    return {
        **seen["differences_clients"],
        **seen["bug_clients"],
        "fresh": seen["fresh_clients"]["fresh"],
    }


def test_every_finder_step_walks_the_route_of_its_own_task(monkeypatch):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", LLMClient())

    steps = step_clients(seen)
    assert set(steps) == {
        "audit",
        "scan",
        "judge",
        "trace",
        "method",
        "concept",
        "checklist",
        "checklist_audit",
        "skeptic",
        "fresh",
    }
    for task, client in steps.items():
        assert [p.name for p in client.chain] == route(task), task
    assert [p.name for p in seen["extract_claims"][1].chain] == route("claims")
    # the new check of a fresh question is the audit, on the audit's route
    assert [p.name for p in seen["fresh_clients"]["audit"].chain] == route("audit")


def test_a_call_that_hangs_is_cut_by_the_stop_of_its_route_and_nothing_waits(
    monkeypatch,
):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", LLMClient())

    steps = step_clients(seen)
    for task, client in steps.items():
        assert client.call_stop == routes.ROUTES[task].stop, task
    # a whole-file call may take longer than a small group call
    assert steps["audit"].call_stop > steps["scan"].call_stop


def test_the_planner_walks_its_route_and_the_callers_client_is_not_changed(
    monkeypatch,
):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    assert [p.name for p in seen["plan"][1].chain] == route("plan")
    assert client.chain == CHAIN


def test_the_answer_walks_the_route_of_the_number_of_files(monkeypatch):
    seen = capture(monkeypatch)
    tasks = []
    monkeypatch.setattr(
        asking, "for_task", lambda client, task, **kw: tasks.append(task) or client
    )

    asking._ask_graph("conn", "client")
    tasks.clear()
    for files in (0, 1, 2):
        seen["generate_for_files"](files)

    assert tasks == ["respond_chat", "respond_one", "respond_two"]


def test_two_files_is_the_route_of_the_plain_generate(monkeypatch):
    seen = capture(monkeypatch)
    tasks = []
    monkeypatch.setattr(
        asking, "for_task", lambda client, task, **kw: tasks.append(task) or client
    )

    asking._ask_graph("conn", "client")

    assert tasks.count("respond_two") == 1
    assert callable(seen["generate"]) and callable(seen["generate_for_files"])


def test_the_answer_asks_for_as_many_tokens_as_its_kind_needs(monkeypatch):
    seen = capture(monkeypatch)
    asked = []

    class Client:
        def generate(self, prompt, *, max_tokens):
            asked.append(max_tokens)

    monkeypatch.setattr(asking, "for_task", lambda client, task, **kw: Client())

    asking._ask_graph("conn", "client")
    for files in (0, 1, 2, 3):
        seen["generate_for_files"](files)("a prompt")

    assert asked == [8_000, 16_000, 32_000, 32_000]
