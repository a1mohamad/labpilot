"""The pause that asks the person one question just before the answer (D109).

Fakes and an in-memory saver: what is checked is the graph's behaviour at the
pause, not the database.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from labpilot.agent import Plan, ask_the_user, build_graph
from labpilot.agent.ask_user import MAX_REPLY_CHARS, SKIPPED, clean_reply


def run(ask_text: str, replies: list, *, pause: bool = True):
    """Run one message; return (outputs, prompts seen, calls of each node)."""
    prompts: list[str] = []
    calls = {"plan": 0, "generate": 0, "make_prompt": 0}

    def make_prompt(chunks, question, user_reply="", **_):
        calls["make_prompt"] += 1
        prompts.append(user_reply)
        return "the prompt", chunks

    def plan(question, a, b):
        calls["plan"] += 1
        return Plan(steps=(), queries=(), ask=ask_text)

    def generate(prompt):
        calls["generate"] += 1
        return "the answer"

    graph = build_graph(
        measure=lambda a, b: {"A": "x"},
        fits=lambda sides, question, last_answer: True,
        stuff=lambda sides, question: ((), None),
        search_one=lambda sides, query: (),
        totals_of=lambda sides: {},
        rank_side=lambda question, pile: pile,
        plan=plan,
        make_prompt=make_prompt,
        generate=generate,
        ask=ask_the_user if pause else None,
        checkpointer=InMemorySaver() if pause else None,
    )
    config = {"configurable": {"thread_id": "t"}}
    outputs = [graph.invoke({"question": "why lower?", "a": "A-1", "b": ""}, config)]
    for reply in replies:
        outputs.append(graph.invoke(Command(resume=reply), config))
    return outputs, prompts, calls


def test_no_question_in_the_plan_means_no_pause():
    outputs, prompts, calls = run("", [])

    assert "__interrupt__" not in outputs[0]
    assert outputs[0]["result"] == "the answer"
    assert prompts == [""]


def test_a_question_pauses_the_graph_before_the_answer_is_written():
    outputs, prompts, calls = run("What F1 did you get?", [])

    paused = outputs[0]
    assert paused["__interrupt__"][0].value == {"question": "What F1 did you get?"}
    assert "result" not in paused
    assert calls["generate"] == 0


def test_the_reply_reaches_the_prompt_and_the_work_before_the_pause_is_not_redone():
    outputs, prompts, calls = run("What F1 did you get?", ["0.82 on validation"])

    assert outputs[1]["result"] == "the answer"
    assert prompts == ["Asked: What F1 did you get?\nAnswer: 0.82 on validation"]
    assert calls == {"plan": 1, "make_prompt": 1, "generate": 1}


def test_a_skipped_question_gives_a_normal_answer_with_no_note():
    outputs, prompts, calls = run("What F1 did you get?", [SKIPPED])

    assert outputs[1]["result"] == "the answer"
    assert prompts == [""]


def test_a_graph_with_no_saver_never_pauses_even_when_the_plan_asks():
    outputs, prompts, calls = run("What F1 did you get?", [], pause=False)

    assert outputs[0]["result"] == "the answer"
    assert prompts == [""]


def test_a_reply_is_text_trimmed_and_capped():
    assert clean_reply("  0.82  ") == "0.82"
    assert len(clean_reply("x" * (MAX_REPLY_CHARS + 50))) == MAX_REPLY_CHARS
    assert clean_reply(None) == SKIPPED
    assert clean_reply({"skip": True}) == SKIPPED
