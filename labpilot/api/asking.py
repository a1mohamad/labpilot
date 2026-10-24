from __future__ import annotations

import logging
from functools import partial

import psycopg
from langgraph.graph.state import CompiledStateGraph
from psycopg_pool import ConnectionPool

from labpilot.agent import CheckError, build_graph
from labpilot.api.chains import for_claims
from labpilot.api.checking import make_checker
from labpilot.api.checkpoints import open_saver, prune
from labpilot.api.claims import make_claims_extractor
from labpilot.api.contracts import Comparison
from labpilot.api.differences import make_difference_finder
from labpilot.api.errors import (
    ArtifactChanged,
    EmbeddingUnavailable,
    GenerationUnavailable,
    InvalidQuestion,
)
from labpilot.api.file_facts import FileFacts
from labpilot.api.followups import last_answer_text, make_rewriter
from labpilot.api.planning import make_planner
from labpilot.api.prompting import build_answer_prompt
from labpilot.api.reading import fits_whole, measure_sides, stuffed_chunks
from labpilot.api.requery import make_query_writer
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
) -> Comparison:
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
    graph = _ask_graph(conn, client, thread_id, pool)
    start = {"question": question, "a": a_id, "b": b_id}
    if thread_id is None:
        final = graph.invoke(start)
    else:
        config = {"configurable": {"thread_id": thread_id}}
        final = graph.invoke(start, config, durability="exit")
        _forget_old_copies(_saving_place(conn, pool), thread_id)
    return Comparison(
        result=final["result"],
        chunks=final["chunks"],
        selected=final["selected"],
        prompt=final["prompt"],
        totals=final["totals"],
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
) -> CompiledStateGraph:
    """The graph ask() runs, with the real functions handed to it.

    labpilot/agent/ may not import store/, llm/ or this module, so it receives
    these six functions instead. Each one is a step ask() used to do inline, and
    each keeps the conversion of errors that belongs to the API layer.
    """

    def fits(sides, question):
        return fits_whole(sides, question=question)

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

    def search_claim(sides, query):
        # The check of a claim is a safety net (D39). When its search fails, the
        # claim is left unchecked and the answer goes on. The question's own
        # search keeps raising, because without it there is no answer.
        try:
            return search_one(sides, query)
        except (EmbeddingUnavailable, ArtifactChanged, psycopg.Error) as exc:
            raise CheckError(f"the search for a claim failed: {exc}") from exc

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
    whole_files = FileFacts(conn)

    return build_graph(
        measure=partial(measure_sides, conn),
        fits=fits,
        stuff=stuff_sides,
        search_one=search_one,
        totals_of=totals_of,
        rank_side=rank_pile,
        plan=make_planner(conn, client),
        summarize=summarize,
        extract_claims=make_claims_extractor(conn, claims_client),
        check=make_checker(claims_client, whole_files.facts_for),
        search_claim=search_claim,
        new_query=make_query_writer(claims_client, whole_files.outline),
        find_missing=make_difference_finder(conn, claims_client, whole_files),
        whole_side=whole_side,
        make_prompt=build_answer_prompt,
        rewrite=make_rewriter(client),
        answer_text=last_answer_text,
        generate=generate,
        checkpointer=open_saver(_saving_place(conn, pool)) if thread_id else None,
    )
