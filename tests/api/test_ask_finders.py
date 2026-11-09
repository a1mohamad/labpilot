from labpilot.api import asking
from labpilot.llm import CHAIN, GEMINI_3_1_FLASH_LITE, GEMINI_3_5_FLASH_LITE, LLMClient


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    def fake_differences(conn, *, whole, small, merge):
        seen["differences_clients"] = (whole, small)
        return "find_differences"

    def fake_bugs(conn, *, client, skeptic_client, trace_client):
        seen["bug_clients"] = (client, skeptic_client, trace_client)
        return "find_bugs"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(asking, "make_planner", lambda conn, client: ("plan", client))
    monkeypatch.setattr(
        asking, "make_claims_extractor", lambda conn, client: ("extract", client)
    )
    monkeypatch.setattr(asking, "make_find_differences", fake_differences)
    monkeypatch.setattr(asking, "make_bug_finder", fake_bugs)
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


def test_the_claims_and_the_differences_start_with_flash_lite(monkeypatch):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", LLMClient())

    whole, small = seen["differences_clients"]
    for client in (seen["extract_claims"][1], whole, small):
        assert client.chain[0].model == GEMINI_3_5_FLASH_LITE.model
        assert len(client.chain) == len(CHAIN)


def test_every_finder_call_has_a_time_limit_and_a_small_call_no_second_try(
    monkeypatch,
):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", LLMClient())

    whole, small = seen["differences_clients"]
    hunt, skeptic, trace = seen["bug_clients"]
    for client in (whole, hunt, skeptic):
        assert client.total_budget == 300.0
        assert {tier.timeout for tier in client.chain} == {(10.0, 120.0)}
    for client in (small, trace):
        assert client.total_budget == 150.0
        assert client.max_retries_per_tier == 0
        assert {tier.timeout for tier in client.chain} == {(10.0, 40.0)}


def test_the_trace_of_the_bug_hunt_starts_with_flash_lite_3_1(monkeypatch):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", LLMClient())

    assert seen["bug_clients"][2].chain[0].model == GEMINI_3_1_FLASH_LITE.model


def test_the_planner_and_the_client_the_caller_gave_keep_their_own_chain(monkeypatch):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    assert seen["plan"][1] is client
    assert client.chain == CHAIN
