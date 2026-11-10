from collections.abc import Sequence

from labpilot._text import truncate
from labpilot.prompts.instructions import Instructions

FOLLOW_UP_VERSION = 1
FOLLOW_UP_MAX_TOKENS = 3_000
RECENT_QUESTIONS = 4
QUESTION_CHARS = 300
# The shortest cut of an answer, for a caller that wants only its end.
LAST_ANSWER_CHARS = 2_000
# The chat keeps the WHOLE last answer, and the answer prompt reads all of
# it (D104): a report is about 10,000 to 20,000 characters, and a follow-up
# such as "fix bug 3" needs the part that names bug 3. This is only a cap.
KEPT_ANSWER_CHARS = 20_000
MAX_REWRITE_CHARS = 600

FOLLOW_UP = Instructions(
    name="follow_up",
    header="""\
A person is chatting with a tool that reads their papers and code.
They wrote a new question. It may depend on the chat before it: it may say
"it", "that" or "the second one", or be only "and the learning rate?".

You get their earlier questions and, if there is one, the last answer the tool
gave. Rewrite the new question so that a reader who has not seen the chat can
understand it alone.
- If the new question already makes sense alone, copy it exactly.
- If you cannot tell what a word points to, copy the new question exactly.
  Never guess.
- Otherwise replace each word that points back with what it means. Use the
  earlier questions. Use the last answer only when the new question points at
  it, for example "the second one" or "yes".
- Do not answer the question. Do not add anything the person did not ask.
- Write one question on one line and nothing else: no quotes, no explanation.

Two examples.
Earlier: how is the data split?
New: and the seed?
Answer: how is the seed set for the data split?

Earlier: what does train.py do?
New: why is that one slow?
Answer: why is that one slow?
(It is copied, because "that one" could be many things.)""",
    closing="Write the rewritten question now.",
)


def last_answer_excerpt(text: str, chars: int = LAST_ANSWER_CHARS) -> str:
    """The END of an answer, because an offer or a list of options comes last.

    The result is never longer than `chars`, so cutting it again changes
    nothing.
    """
    text = text.strip()
    if len(text) <= chars:
        return text
    return "…" + text[-(chars - 1) :]


def kept_answer(text: str) -> str:
    """The last answer as the chat keeps it: whole, up to KEPT_ANSWER_CHARS."""
    return last_answer_excerpt(text, KEPT_ANSWER_CHARS)


def last_answer_block(last_answer: str, chars: int = LAST_ANSWER_CHARS) -> str:
    answer = last_answer_excerpt(last_answer, chars)
    return f"The last answer the tool gave:\n{answer}" if answer else ""


def build_follow_up_prompt(
    question: str, history: Sequence[str], last_answer: str = ""
) -> str:
    if not question.strip():
        raise ValueError("a follow-up needs a question")
    if not history:
        raise ValueError("a follow-up needs an earlier question")

    earlier = "\n".join(
        f"{number}. {truncate(text, QUESTION_CHARS)}"
        for number, text in enumerate(history[-RECENT_QUESTIONS:], start=1)
    )
    blocks = [FOLLOW_UP.header, f"Earlier questions, oldest first:\n{earlier}"]
    # The WHOLE kept answer (D104): "the first difference" points at the start
    # of a list. Measured 2026-11-10 on the OTP pair: with only the last 2,000
    # characters the rewrite copied the question 2 of 2 times (and once named
    # the wrong difference in the real chat); with the whole answer it named
    # the right one 2 of 2 times.
    if answer_block := last_answer_block(last_answer, KEPT_ANSWER_CHARS):
        blocks.append(answer_block)
    blocks.append(f"New question:\n{question.strip()}")
    blocks.append(FOLLOW_UP.closing)
    return "\n\n".join(blocks)


def follow_up_problem(question: str, answer: str) -> str | None:
    text = answer.strip()
    if not text:
        return "the answer is blank"
    if "\n" in text:
        return "the answer has more than one line"
    # A copy of the question is always allowed, however long the question is.
    if len(text) > max(MAX_REWRITE_CHARS, len(question)):
        return f"the answer is {len(text)} characters long"
    return None
