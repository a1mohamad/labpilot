from __future__ import annotations

import logging
from functools import partial

import psycopg
from langgraph.graph.state import CompiledStateGraph

from labpilot.agent import build_graph
from labpilot.api.checkpoints import open_saver, prune
from labpilot.api.contracts import Comparison
from labpilot.api.errors import (
    GenerationUnavailable,
    InvalidQuestion,
)
from labpilot.api.prompting import build_report_prompt
from labpilot.api.reading import fits_whole, measure_sides, stuffed_chunks
from labpilot.api.searching import retrieved_chunks
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.prompts import (
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
) -> Comparison:
    """Answer a question about two STORED artifacts.

    The ladder, and step 1 is the one that keeps being under-weighted:

        1  do A and B TOGETHER fit?  -> read every row back, STUFF, and neither
           embed nor search nor rerank runs at all
        2  otherwise search per side, gate, rerank per side, never merged

    Stuffing is not a shortcut. When the corpus fits, retrieval is not neutral
    but HARMFUL: a bad retriever can hide the very line the report needed.
    """
    if not question.strip():
        raise InvalidQuestion("question must not be empty")

    graph = _ask_graph(conn, client, thread_id)
    start = {"question": question, "a": a_id, "b": b_id}
    if thread_id is None:
        final = graph.invoke(start)
    else:
        config = {"configurable": {"thread_id": thread_id}}
        final = graph.invoke(start, config, durability="exit")
        _forget_old_copies(conn, thread_id)
    return Comparison(
        result=final["result"],
        chunks=final["chunks"],
        selected=final["selected"],
        prompt=final["prompt"],
        totals=final["totals"],
    )


def _forget_old_copies(conn: psycopg.Connection, thread_id: str) -> None:
    try:
        prune(conn, thread_id)
    except psycopg.Error:
        logger.warning(
            "could not delete old copies of chat %s", thread_id, exc_info=True
        )


def _ask_graph(
    conn: psycopg.Connection, client: LLMClient, thread_id: str | None = None
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

    def search_sides(sides, question):
        chunks = retrieved_chunks(conn, sides, question=question)
        return chunks, {side: found.chunks for side, found in sides.items()}

    def make_prompt(chunks, question, totals):
        return build_report_prompt(chunks, question=question, totals=totals)

    def generate(prompt):
        try:
            return client.generate(prompt, max_tokens=REPORT_MAX_TOKENS)
        except AllFreeTiersExhausted as exc:
            raise GenerationUnavailable(
                "every free tier failed", attempts=exc.attempts
            ) from exc

    return build_graph(
        measure=partial(measure_sides, conn),
        fits=fits,
        stuff=stuff_sides,
        search=search_sides,
        make_prompt=make_prompt,
        generate=generate,
        checkpointer=open_saver(conn) if thread_id else None,
    )
