from labpilot.api import asking, followups


def capture(monkeypatch):
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(asking, "make_planner", lambda conn, client: "planner")
    return seen


def test_the_graph_gets_the_rewriter_made_from_the_client(monkeypatch):
    seen = capture(monkeypatch)
    made = []

    def fake_make_rewriter(client):
        made.append(client)
        return "the rewriter"

    monkeypatch.setattr(asking, "make_rewriter", fake_make_rewriter)

    asking._ask_graph("conn", "client")

    assert seen["rewrite"] == "the rewriter"
    assert made == ["client"]


def test_the_graph_gets_the_function_that_saves_the_last_answer(monkeypatch):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert seen["answer_text"] is followups.last_answer_text
