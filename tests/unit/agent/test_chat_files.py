"""One chat, a different number of files at each message.

An artifact is STATE: it is stored once, when the person adds it, and every
message sends the ids the person has at that moment. So within one chat the
number of files can grow (a question with no file, then one file, then two) and
it can shrink (after a page refresh the page sends only what it remembers).
Fakes and an in-memory saver: what is checked is the graph, not the database.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import Plan, build_graph


def run_chat(turns):
    seen = []

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        seen.append(
            {"files": files, "summaries": dict(summaries), "last_answer": last_answer}
        )
        return "the prompt", chunks

    graph = build_graph(
        measure=lambda a, b: {s: "stored" for s, i in (("A", a), ("B", b)) if i},
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((), None),
        search_one=lambda sides, query: (),
        totals_of=lambda sides: {},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: Plan(steps=(), queries=()),
        make_prompt=make_prompt,
        generate=lambda prompt: f"answer {len(seen)}",
        summarize=lambda artifact_id: f"summary of {artifact_id}",
        answer_text=lambda result: result,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "one-chat"}}
    for number, (a, b) in enumerate(turns, start=1):
        graph.invoke({"question": f"question {number}", "a": a, "b": b}, config)

    return seen


def test_a_chat_can_grow_from_no_file_to_two():
    seen = run_chat([("", ""), ("", "B-1"), ("A-1", "B-1")])

    assert [message["files"] for message in seen] == [0, 1, 2]
    assert [message["summaries"] for message in seen] == [
        {"A": "", "B": ""},
        {"A": "", "B": "summary of B-1"},
        {"A": "summary of A-1", "B": "summary of B-1"},
    ]


def test_the_last_answer_follows_the_chat_whatever_the_number_of_files():
    seen = run_chat([("", ""), ("", "B-1"), ("A-1", "B-1")])

    assert [message["last_answer"] for message in seen] == [
        "",
        "answer 1",
        "answer 2",
    ]


def test_a_file_left_out_of_a_message_leaves_no_summary_behind():
    """Message 2 sends no A. Message 1's summary of A must not come along.

    Without this the saved chat kept it, and the prompt described a file that
    the question did not have.
    """
    seen = run_chat([("A-1", "B-1"), ("", "B-1")])

    assert seen[0]["summaries"] == {"A": "summary of A-1", "B": "summary of B-1"}
    assert seen[1]["files"] == 1
    assert seen[1]["summaries"] == {"A": "", "B": "summary of B-1"}
