from typing import Any

from langgraph.types import interrupt

from labpilot.agent.plan import Plan

# What the person typed is capped, because it goes into the prompt as it is.
MAX_REPLY_CHARS = 1_000

# A skip is the empty text. It is NOT None: `Command(resume=None)` crashes
# LangGraph 1.2.12 (`resume_is_map` is used before it is set), measured on
# 2026-11-12.
SKIPPED = ""


def clean_reply(reply: Any) -> str:
    """What the person answered, as a short plain text. A skip gives ""."""
    if not isinstance(reply, str):
        return SKIPPED
    return reply.strip()[:MAX_REPLY_CHARS]


def ask_the_user(state: dict[str, Any]) -> str:
    """Pause the graph with the planner's question and return the exchange.

    The result is "Asked: <question>" and "Answer: <reply>" on two lines, or ""
    when there was no question or the person skipped it.

    No question in the plan means no pause. LangGraph saves the graph at the
    pause, the run returns to the caller with the question, and the next call
    with `Command(resume=reply)` starts THIS function again from its first
    line: `interrupt` then returns the reply at once. So nothing may come
    before it that is slow or not repeatable.
    """
    plan = state.get("plan")
    question = plan.ask if isinstance(plan, Plan) else ""
    if not question:
        return SKIPPED
    reply = clean_reply(interrupt({"question": question}))
    return f"Asked: {question}\nAnswer: {reply}" if reply else SKIPPED
