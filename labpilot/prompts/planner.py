from collections.abc import Sequence

from labpilot.prompts.corpus_map import PLANNER_BUDGET

# The wording below is FIXED. Change it only together with this number, and the
# number is logged beside every plan, so a plan can be tied to its wording.
PLANNER_VERSION = 6

# The answer is a short plan, but a tier that thinks spends tokens first, so
# this is only a backstop. A small number would give such a tier an empty
# answer and waste it.
PLANNER_MAX_TOKENS = 4_000

# What the WHOLE planner prompt may cost, in the estimate the length check uses.
#
# Gemma's input cap is 16,000 tokens a minute and the check pads the estimate by
# 10%, so the largest prompt it accepts is 16,000 / 1.1 = 14,545. Gemma has the
# largest free quota here, so the planner is built to fit it. A test ties this
# number to the cap in the registry.
PLANNER_INPUT_LIMIT = 14_500

STEP_MEANINGS: dict[str, str] = {
    "summarize": "write a short summary of each file",
    "find_differences": "compare A and B both ways: what B does otherwise or "
    "leaves out of what A states, and what B does that A never says",
    "find_bugs": "read B alone and look for its defects: in the code, the "
    "logic, the method, the numbers and the idea itself",
}

PLANNER = (
    "You are the planner of LabPilot. LabPilot compares two files: A is the "
    "reference (for example a paper) and B is the work being checked (for "
    "example code). It explains why their results differ.\n\n"
    "You do not answer the question. You decide what LabPilot does, by calling "
    "make_plan once.\n\n"
    "steps: what to run. Use only the steps listed below, and choose the "
    "fewest that answer the question. An empty list is allowed.\n"
    "queries: what to look for in the files. Each query is a short piece of "
    "text that would appear in the file itself (a value, a name, a phrase), "
    "never a question, and it names the side it is for.\n"
    'Good query: "learning rate 3e-4 cosine decay". '
    'Bad query: "what learning rate is used?"\n\n'
    "about: which file the question is about, A, B or both. Say A or B only "
    "when the question names one file, or one thing that only that file holds. "
    "A comparison, or a question that is not clear, is both.\n"
    "files: false only when the question can be answered without reading any "
    "file (a general question, or thanks). When you are not sure, true.\n"
    "fresh: true when the question asks whether a file does or has ONE "
    "specific thing, a yes or no check of one named behavior that a general "
    "comparison would not look at (for example: does it clip the gradient, "
    "does it raise an error for a negative value). False when the question "
    "asks what the files say, where something is, how it works, why results "
    "differ, for a summary, a comparison or the bugs. When you are not sure, "
    "false.\n"
    "ask: usually empty. Write one short question for the person only when they "
    "speak about their OWN result and do not say what it is or how it was "
    "measured (for example: my numbers came out lower). At most two short "
    "lines. Never repeat or reword the person's own question. When you are not "
    "sure, leave it empty.\n\n"
    "The map lists the parts of each file with their line numbers. A signature "
    "or a sentence in quotes was copied from the file itself, so its words are "
    "good words for a query."
)


def build_planner_prompt(
    question: str, corpus_map: str, steps: Sequence[str], *, max_queries: int
) -> str:
    for step in steps:
        if step not in STEP_MEANINGS:
            raise ValueError(f"no meaning is written for the step {step!r}")

    listed = "\n".join(f"- {step}: {STEP_MEANINGS[step]}" for step in steps)
    return (
        f"{PLANNER}\n"
        f"Write 2 to 5 queries, and never more than {max_queries}. "
        "The question itself is searched too, so do not copy it.\n\n"
        f"STEPS YOU MAY CHOOSE\n{listed}\n\n"
        f"WHAT THE FILES CONTAIN\n{corpus_map}\n\n"
        f"THE QUESTION\n{question}"
    )


def map_budget(fixed_tokens: int) -> int:
    room = PLANNER_INPUT_LIMIT - fixed_tokens
    return max(1, min(PLANNER_BUDGET, room))
