from collections.abc import Sequence

from labpilot._text import truncate
from labpilot.prompts.instructions import Instructions

FOLLOW_UP_VERSION = 1
FOLLOW_UP_MAX_TOKENS = 3_000
RECENT_QUESTIONS = 4
QUESTION_CHARS = 300
LAST_ANSWER_CHARS = 2_000
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


def last_answer_excerpt(text: str) -> str:
    """The END of an answer, because an offer or a list of options comes last.

    The result is never longer than LAST_ANSWER_CHARS, so cutting it again
    changes nothing.
    """
    text = text.strip()
    if len(text) <= LAST_ANSWER_CHARS:
        return text
    return "…" + text[-(LAST_ANSWER_CHARS - 1) :]


def last_answer_block(last_answer: str) -> str:
    answer = last_answer_excerpt(last_answer)
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
    if answer_block := last_answer_block(last_answer):
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
