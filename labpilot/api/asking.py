from __future__ import annotations

import logging
from functools import partial

import psycopg
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from psycopg_pool import ConnectionPool

from labpilot.agent import ask_the_user, build_graph
from labpilot.api.bugs import make_bug_finder
from labpilot.api.chains import bounded, for_claims, for_skeptic, for_trace
from labpilot.api.checkpoints import open_saver, prune
from labpilot.api.claims import make_claims_extractor
from labpilot.api.contracts import Comparison, Question
from labpilot.api.difference_finder import make_find_differences
from labpilot.api.difference_review import make_merger
from labpilot.api.errors import GenerationUnavailable, InvalidQuestion, NothingToAnswer
from labpilot.api.followups import last_answer_text, make_rewriter
from labpilot.api.gate import halt_answer, make_gate
from labpilot.api.planning import make_planner
from labpilot.api.prompting import build_answer_prompt
from labpilot.api.reading import fits_whole, measure_sides, stuffed_chunks
from labpilot.api.saved import (
    SavedResults,
    saved_bugs,
    saved_claims,
    saved_differences,
    with_saved_steps,
)
from labpilot.api.searching import embed_query, rank_pile, retrieve_query
from labpilot.api.summaries import make_summarizer
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import (
    A_WHOLE_TOKENS,
    REPORT_MAX_TOKENS,
)

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
    graph = _ask_graph(conn, client, thread_id, pool, saved=saved)
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


def _ask_graph(
    conn: psycopg.Connection,
    client: LLMClient,
    thread_id: str | None = None,
    pool: ConnectionPool | None = None,
    *,
    saved: SavedResults | None = None,
) -> CompiledStateGraph:
    """The graph ask() runs, with the real functions handed to it.

    labpilot/agent/ may not import store/, llm/ or this module, so it receives
    these six functions instead. Each one is a step ask() used to do inline, and
    each keeps the conversion of errors that belongs to the API layer.
    """

    def fits(sides, question, last_answer):
        return fits_whole(sides, question=question, last_answer=last_answer)

    def stuff_sides(sides, question):
        return stuffed_chunks(conn, sides), None

    def search_one(sides, query):
        if pool is None:
            return retrieve_query(conn, sides, side=query.side, text=query.text)
        # Embed BEFORE a connection is taken from the pool, so the pool is not
        # held while the embedder answers (R16).
        vector = embed_query(sides, side=query.side, text=query.text)
        if pool.closed:
            pool.open(wait=False)
        for attempt in range(2):
            try:
                with pool.connection() as pooled:
                    return retrieve_query(
                        pooled,
                        sides,
                        side=query.side,
                        text=query.text,
                        vector=vector,
                    )
            except psycopg.OperationalError:
                # A pooled connection the server closed in the middle of the
                # search (seen on 2026-10-24: "SSL SYSCALL EOF"). The pool
                # drops it, and the search is tried once on another (R10).
                if attempt:
                    raise
                logger.warning("a pooled connection died, searching again")
        raise AssertionError("unreachable")

    def whole_side(sides, side):
        # The reference is read whole when it is as small as the step that puts
        # it beside B allows (A_WHOLE_TOKENS); B never is, on this path.
        found = sides[side]
        if side != "A" or found.characters / 3 > A_WHOLE_TOKENS:
            return None
        return stuffed_chunks(conn, {side: found})

    def totals_of(sides):
        return {side: found.chunks for side, found in sides.items()}

    summarizer = make_summarizer(conn, client)

    def summarize(artifact_id):
        # A summary is a guide, not the evidence: when every tier fails the
        # report is still written, from the parts alone.
        try:
            return summarizer(artifact_id)
        except GenerationUnavailable:
            logger.warning(
                "no summary of %s: every tier failed", artifact_id, exc_info=True
            )
            return ""

    def generate(prompt):
        try:
            return client.generate(prompt, max_tokens=REPORT_MAX_TOKENS)
        except AllFreeTiersExhausted as exc:
            raise GenerationUnavailable(
                "every free tier failed", attempts=exc.attempts
            ) from exc

    claims_client = for_claims(client)
    # Time limits (D102): a call that reads a big group waits at most 120 s for
    # a tier and 300 s in all, a small call 40 s and 150 s with no second try,
    # so one slow provider cannot use up the answer.
    whole = bounded(claims_client, read=120.0, budget=300.0)
    small = bounded(claims_client, read=40.0, budget=150.0, retries=0)
    # The merge of the differences: a strong model first with a short limit,
    # then Flash-Lite (the Flash-Lite merge alone missed obvious repeats).
    strong_merge = bounded(client, read=40.0, budget=60.0, retries=0)

    # D104: the claims, the differences and the bugs of these files are made
    # once and read again by the next message or chat with the same files.
    saved = saved if saved is not None else SavedResults(conn)

    return build_graph(
        measure=partial(measure_sides, conn),
        fits=fits,
        stuff=stuff_sides,
        search_one=search_one,
        totals_of=totals_of,
        rank_side=rank_pile,
        plan=with_saved_steps(saved, make_planner(conn, client)),
        summarize=summarize,
        extract_claims=saved_claims(saved, make_claims_extractor(conn, claims_client)),
        find_differences=saved_differences(
            saved,
            make_find_differences(
                conn,
                whole=whole,
                small=small,
                merge=make_merger(strong_merge, small),
            ),
        ),
        find_bugs=saved_bugs(
            saved,
            make_bug_finder(
                conn,
                client=bounded(client, read=120.0, budget=300.0),
                skeptic_client=bounded(for_skeptic(client), read=120.0, budget=300.0),
                trace_client=bounded(
                    for_trace(client), read=40.0, budget=150.0, retries=0
                ),
            ),
        ),
        final_merge=make_merger(small),
        ask=ask_the_user if thread_id else None,
        whole_side=whole_side,
        make_prompt=build_answer_prompt,
        rewrite=make_rewriter(client),
        answer_text=last_answer_text,
        gate=make_gate(claims_client),
        halt_answer=halt_answer,
        generate=generate,
        checkpointer=open_saver(_saving_place(conn, pool)) if thread_id else None,
    )
