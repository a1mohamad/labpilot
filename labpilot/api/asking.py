from __future__ import annotations

import logging
from functools import partial

import psycopg
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from psycopg_pool import ConnectionPool

from labpilot.agent import ask_the_user, build_graph
from labpilot.api.answering import answerer
from labpilot.api.bugs import make_bug_finder
from labpilot.api.chains import for_task
from labpilot.api.checkpoints import open_saver, prune
from labpilot.api.claims import make_claims_extractor
from labpilot.api.contracts import Comparison, Question
from labpilot.api.difference_finder import make_find_differences
from labpilot.api.difference_review import make_merger
from labpilot.api.errors import InvalidQuestion, NothingToAnswer
from labpilot.api.followups import last_answer_text, make_rewriter
from labpilot.api.fresh import make_fresh_check
from labpilot.api.gate import halt_answer, make_gate
from labpilot.api.planning import make_planner
from labpilot.api.prompting import build_answer_prompt
from labpilot.api.reading import fits_whole, measure_sides, stuffed_chunks, whole_side
from labpilot.api.saved import (
    SavedResults,
    saved_bugs,
    saved_claims,
    saved_differences,
    saved_fresh,
    saved_gate,
    saved_summary,
    with_saved_steps,
)
from labpilot.api.searching import rank_pile, search_one
from labpilot.api.summaries import make_summarizer, or_no_summary, summary_chain
from labpilot.ingest import Side
from labpilot.llm import LLMClient

logger = logging.getLogger(__name__)


def ask(
    conn: psycopg.Connection,
    a_id: str,
    b_id: str,
    *,
    question: str,
    client: LLMClient,
    thread_id: str | None = None,
    pool: ConnectionPool | None = None,
    reply: str | None = None,
    fast: bool = False,
) -> Comparison | Question:
    """Answer a question about up to two STORED artifacts.

    An empty id means "no file in that slot". With no file the answer is a chat
    answer, with one file it is an answer about that file, with two it is the
    report.

    The ladder, and step 1 is the one that keeps being under-weighted:

        1  do A and B TOGETHER fit?  -> read every row back, STUFF, and neither
           embed nor search nor rerank runs at all
        2 otherwise the planner writes queries, each is searched alone, and
            each side is reranked once.

    Stuffing is not a shortcut. When the corpus fits, retrieval is not neutral
    but HARMFUL: a bad retriever can hide the very line the report needed.
    """
    if not question.strip():
        raise InvalidQuestion("question must not be empty")

    a_id, b_id = _in_their_own_slots(a_id, b_id)
    saved = SavedResults(conn)
    graph = _ask_graph(conn, client, thread_id, pool, saved=saved, fast=fast)
    start = {"question": question, "a": a_id, "b": b_id}
    if thread_id is None:
        final = graph.invoke(start)
    else:
        config = {"configurable": {"thread_id": thread_id}}
        # A reply goes on from the pause the last call left. The empty text is a
        # skip. It is never None: `Command(resume=None)` crashes LangGraph 1.2.12.
        if reply is not None and not graph.get_state(config).next:
            raise NothingToAnswer("this chat is not waiting for an answer")
        given = start if reply is None else Command(resume=reply)
        final = graph.invoke(given, config, durability="exit")
        _forget_old_copies(_saving_place(conn, pool), thread_id)
    if "__interrupt__" in final:
        return Question(text=final["__interrupt__"][0].value["question"])
    return Comparison(
        result=final["result"],
        chunks=final["chunks"],
        selected=final["selected"],
        prompt=final["prompt"],
        totals=final["totals"],
        reused=tuple(saved.reused),
    )


def _in_their_own_slots(a_id: str, b_id: str) -> tuple[str, str]:
    """Put a LONE artifact in the slot of its own side.

    The id carries its side (`A-9f2c...`, `B-3e8a...`), and the graph reads slot
    `a` as side A and slot `b` as side B: the planner writes queries for the
    sides that exist, `fan_out` searches them, and the summaries are labelled
    by slot. So a subject sent alone in slot `a` would be searched as a side A
    this question does not have, and the search would fail on a missing key.

    With two ids, or with none, nothing moves. Two ids is the old behaviour,
    and `measure_sides` already refuses two ids of one side.
    """
    if bool(a_id) == bool(b_id):
        return a_id, b_id

    lone = a_id or b_id
    if lone.startswith("A-"):
        return lone, ""
    if lone.startswith("B-"):
        return "", lone

    return a_id, b_id


def _saving_place(
    conn: psycopg.Connection, pool: ConnectionPool | None
) -> psycopg.Connection | ConnectionPool:
    """Where the chat is saved and pruned: the pool when there is one.

    The save runs at the END of a message, after a report that can take many
    minutes. The connection of the request sat idle all that time, and on
    2026-10-25 such a connection was closed by the server after a 7.5-minute
    report ("server closed the connection unexpectedly"), so the answer would
    have been lost at the save. A pool checks a connection before it hands it
    out.
    """
    if pool is None:
        return conn
    if pool.closed:
        pool.open(wait=False)
    return pool


def _forget_old_copies(
    conn: psycopg.Connection | ConnectionPool, thread_id: str
) -> None:
    try:
        prune(conn, thread_id)
    except psycopg.Error:
        logger.warning(
            "could not delete old copies of chat %s", thread_id, exc_info=True
        )


def _fits(sides, question: str, last_answer: str) -> bool:
    return fits_whole(sides, question=question, last_answer=last_answer)


def _stuff(conn: psycopg.Connection, sides, question: str):
    return stuffed_chunks(conn, sides), None


def _totals_of(sides) -> dict[Side, int]:
    return {side: found.chunks for side, found in sides.items()}


def _ask_graph(
    conn: psycopg.Connection,
    client: LLMClient,
    thread_id: str | None = None,
    pool: ConnectionPool | None = None,
    *,
    saved: SavedResults | None = None,
    fast: bool = False,
) -> CompiledStateGraph:
    """The graph ask() runs, with the real functions handed to it.

    labpilot/agent/ may not import store/, llm/ or this module, so it receives
    these functions instead. Each one keeps the conversion of errors that belongs
    to the API layer.
    """

    # D104 and D110: the stored objects, made once and read again. A summary is a
    # small job: the short chain of D110, with a time limit.
    saved = saved if saved is not None else SavedResults(conn)
    summarizer = saved_summary(saved, make_summarizer(conn, summary_chain(client)))

    audit = for_task(client, "audit")
    merge = for_task(client, "merge")

    return build_graph(
        measure=partial(measure_sides, conn),
        fits=_fits,
        stuff=partial(_stuff, conn),
        search_one=partial(search_one, conn, pool=pool),
        totals_of=_totals_of,
        rank_side=rank_pile,
        plan=with_saved_steps(
            saved, make_planner(conn, for_task(client, "plan")), fast=fast
        ),
        summarize=or_no_summary(summarizer),
        extract_claims=saved_claims(
            saved, make_claims_extractor(conn, for_task(client, "claims"))
        ),
        find_differences=saved_differences(
            saved,
            make_find_differences(
                conn,
                audit=audit,
                scan=for_task(client, "scan"),
                judge_client=for_task(client, "judge"),
                merge=make_merger(for_task(client, "merge_strong"), merge),
            ),
        ),
        find_bugs=saved_bugs(
            saved,
            make_bug_finder(
                conn,
                trace=for_task(client, "trace"),
                method=for_task(client, "method"),
                concept=for_task(client, "concept"),
                checklist=for_task(client, "checklist"),
                checklist_audit=for_task(client, "checklist_audit"),
                skeptic=for_task(client, "skeptic"),
                fast=fast,
            ),
            fast=fast,
        ),
        fresh=saved_fresh(
            saved,
            make_fresh_check(conn, statement=for_task(client, "fresh"), audit=audit),
        ),
        final_merge=make_merger(merge),
        ask=ask_the_user if thread_id else None,
        whole_side=partial(whole_side, conn),
        make_prompt=build_answer_prompt,
        rewrite=make_rewriter(for_task(client, "rewrite")),
        answer_text=last_answer_text,
        gate=saved_gate(saved, make_gate(for_task(client, "gate"))),
        halt_answer=halt_answer,
        generate=answerer(client, 2),
        generate_for_files=partial(answerer, client),
        checkpointer=open_saver(_saving_place(conn, pool)) if thread_id else None,
    )
