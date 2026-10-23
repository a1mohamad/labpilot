from labpilot.api import asking
from labpilot.llm import CHAIN, GEMINI_3_5_FLASH_LITE, LLMClient


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(
        asking, "make_planner", lambda conn, client: ("planner", client)
    )
    monkeypatch.setattr(
        asking, "make_claims_extractor", lambda conn, client: ("extract", client)
    )
    monkeypatch.setattr(asking, "make_checker", lambda client: ("check", client))
    return seen


def test_the_graph_gets_the_function_that_makes_claims_and_the_one_that_checks(
    monkeypatch,
):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert seen["extract_claims"] == ("extract", "client")
    assert seen["check"] == ("check", "client")


def test_both_get_the_same_client_and_it_starts_with_flash_lite(monkeypatch):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    claims_client = seen["extract_claims"][1]
    assert seen["check"][1] is claims_client
    assert claims_client.chain[0].model == GEMINI_3_5_FLASH_LITE.model
    assert len(claims_client.chain) == len(CHAIN)


def test_the_planner_and_the_client_the_caller_gave_keep_their_own_chain(monkeypatch):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    assert seen["plan"][1] is client
    assert client.chain == CHAIN
