# The wording below is FIXED. Change it only together with this number; the number
# is part of the key of a saved result, so a new wording never reads an old one.
FRESH_VERSION = 1

# One short statement is the answer, but a tier that thinks spends tokens first.
FRESH_MAX_TOKENS = 1_000

FRESH_CLAIM = (
    "Rewrite the question as ONE plain statement about the code that is true if "
    "the answer to the question is yes. Write only the statement, on one line. "
    "Do not answer the question."
)


def build_fresh_claim_prompt(question: str) -> str:
    return f"{FRESH_CLAIM}\n\nQUESTION: {question}"
