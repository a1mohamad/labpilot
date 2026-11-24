from labpilot.agent import build_graph  # noqa: F401  (the front door must import)
from labpilot.agent.respond import make_respond_node


def state(**extra):
    base = {"question": "q", "a": "A-1", "b": "B-1", "chunks": ()}
    base.update(extra)
    return base


def node(seen, *, files_to_text=None):
    def make_prompt(chunks, **kwargs):
        seen["files"] = kwargs["files"]
        return "prompt", ()

    def generate(prompt):
        return "plain"

    def for_files(files):
        return lambda prompt: f"routed:{files}"

    return make_respond_node(make_prompt, generate, None, for_files)


def test_the_answer_walks_the_route_of_the_number_of_files():
    seen = {}

    result = node(seen)(state())

    assert seen["files"] == 2
    assert result["result"] == "routed:2"


def test_a_question_about_one_file_walks_the_route_of_one_file():
    from labpilot.agent.plan import Plan

    seen = {}
    plan = Plan(steps=(), queries=(), source="x", about="B")

    result = node(seen)(state(plan=plan))

    assert seen["files"] == 1
    assert result["result"] == "routed:1"


def test_a_chat_question_walks_the_route_of_no_file():
    from labpilot.agent.plan import Plan

    seen = {}
    plan = Plan(steps=(), queries=(), source="x", files=False)

    result = node(seen)(state(plan=plan))

    assert seen["files"] == 0
    assert result["result"] == "routed:0"


def test_without_a_route_picker_the_plain_generate_answers():
    def make_prompt(chunks, **kwargs):
        return "prompt", ()

    result = make_respond_node(make_prompt, lambda prompt: "plain")(state())

    assert result["result"] == "plain"
