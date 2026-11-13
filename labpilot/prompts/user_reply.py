NOTE = (
    "The person was asked one question while the answer was prepared. What they "
    'said below comes from them, not from the files: say "you said" when you use '
    "it, and never present it as something a file shows."
)


def question_with_reply(question: str, exchange: str) -> str:
    """The question, followed by what the person said when they were asked."""
    exchange = exchange.strip()
    if not exchange:
        return question
    return f"{question}\n\n{NOTE}\n{exchange}"
