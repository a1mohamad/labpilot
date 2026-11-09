from labpilot.agent import Bug, Difference
from labpilot.api.finding_lines import (
    BUGS_NOTE,
    DIFFERENCES_NOTE,
    LINE_CHARS,
    bug_line,
    difference_line,
    prior_text,
)
from labpilot.api.prompting import build_answer_prompt
from labpilot.ingest import Chunk
from labpilot.prompts import PRIOR_HEADING, PROMPT_BUDGET
from labpilot.tokens import estimate_tokens


def chunk(index, words=300):
    return Chunk(
        text=" ".join(["word"] * words),
        source="m.py",
        start_line=index,
        end_line=index,
        side="A" if index % 2 else "B",
        artifact_id="X-1",
        chunk_index=index,
    )


def difference(kind="differs", *, text="B uses a bigger step", unclear=False):
    return Difference(
        kind,
        text,
        "[solver.py · lines 1-3]",
        "dt = 0.05",
        fact="the time step is 0.01 s" if kind != "silent" else "",
        unclear=unclear,
    )


def bug(verdict="real", severity="high"):
    return Bug(
        "logic", "the step is never updated", "[solver.py]", "t = 0", severity, verdict
    )


def test_a_line_names_its_kind_what_a_states_and_the_place_in_b():
    line = difference_line(difference())

    assert line.startswith("[B differs] B uses a bigger step")
    assert 'A states: "the time step is 0.01 s"' in line
    assert 'B ([solver.py · lines 1-3]): "dt = 0.05"' in line


def test_each_kind_has_its_own_tag_and_doubt_is_shown():
    assert difference_line(difference("missing")).startswith("[B leaves out]")
    assert difference_line(difference("silent")).startswith("[A silent]")
    assert difference_line(difference(unclear=True)).startswith("[B differs, unclear]")


def test_a_bug_line_names_the_verdict_and_the_kind():
    assert bug_line(bug()).startswith("[real - logic] the step is never updated")


def test_a_long_line_is_cut_at_the_limit():
    line = difference_line(difference(text="x" * 900))

    assert len(line) == LINE_CHARS
    assert line.endswith("…")


def test_a_difference_comes_before_a_silence_and_a_doubtful_line_comes_last():
    text = prior_text(
        [difference("silent"), difference(unclear=True), difference("missing")],
        [],
        limit=10_000,
    )
    lines = text.splitlines()[1:]

    assert [line.split("]")[0] for line in lines] == [
        "[B leaves out",
        "[A silent",
        "[B differs, unclear",
    ]


def test_the_two_kinds_of_finding_sit_in_two_blocks_with_their_notes():
    text = prior_text([difference()], [bug()], limit=10_000)

    assert text.index(DIFFERENCES_NOTE) < text.index(BUGS_NOTE)


def test_no_findings_make_no_block_and_no_change_to_the_prompt():
    chunks = (chunk(0), chunk(1))

    assert prior_text([], [], limit=10_000) == ""
    assert build_answer_prompt(
        chunks, question="why?", files=2, differences=(), bugs=()
    ) == build_answer_prompt(chunks, question="why?", files=2)


def test_the_findings_sit_in_the_prompt_before_the_question():
    chunks = (chunk(0), chunk(1))

    prompt, _ = build_answer_prompt(
        chunks, question="why?", files=2, differences=[difference()], bugs=[bug()]
    )

    assert PRIOR_HEADING in prompt and DIFFERENCES_NOTE in prompt
    assert prompt.index(BUGS_NOTE) < prompt.index("QUESTION: why?")
    assert prompt.index("word word") < prompt.index(PRIOR_HEADING)


def test_with_no_file_there_is_nothing_to_show_and_the_findings_are_ignored():
    prompt, selected = build_answer_prompt(
        (), question="hi", files=0, differences=[difference()]
    )

    assert DIFFERENCES_NOTE not in prompt
    assert selected == ()


def test_twenty_findings_never_push_the_prompt_over_the_budget_or_a_part_out():
    bare = 0
    while True:
        chunks = tuple(chunk(index) for index in range(bare + 1))
        prompt, _ = build_answer_prompt(chunks, question="why?", files=2)
        if estimate_tokens(prompt) > PROMPT_BUDGET - 600:
            break
        bare += 1
    chunks = tuple(chunk(index) for index in range(bare))
    many = [difference(text="x" * 250) for _ in range(20)]

    prompt, selected = build_answer_prompt(chunks, question="why?", files=2)
    assert selected == chunks

    prompt, selected = build_answer_prompt(
        chunks, question="why?", files=2, differences=many
    )

    # Everything was read, so the PARTS come first (2026-10-24: the findings
    # of a stuffed run cut B from 82 parts to 65). The lines get the room left,
    # and the ones that do not fit are counted, never lost silently.
    assert estimate_tokens(prompt) <= PROMPT_BUDGET
    assert selected == chunks
    assert 0 < prompt.count("[B differs]") < 20
    assert "left out for room" in prompt
