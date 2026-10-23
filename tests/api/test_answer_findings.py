from labpilot.agent import Claim, Finding
from labpilot.api.prompting import CHECK_LINE_CHARS, build_answer_prompt, checks_text
from labpilot.ingest import Chunk
from labpilot.prompts import CHECKS_NOTE, PRIOR_HEADING, PROMPT_BUDGET
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


def finding(verdict, *, kind="", quote="dt = 0.05", note="B uses a bigger step"):
    claim = Claim("the time step is 0.01 s", "[paper.md · 4 Setup]", "time step")
    place = "[solver.py · lines 1-3]" if quote else ""
    return Finding(claim, verdict, kind, place, quote, note)


def test_a_mismatch_comes_first_and_a_match_comes_last():
    text = checks_text(
        [
            finding("match"),
            finding("unchecked", quote="", note=""),
            finding("absent", quote="", note=""),
            finding("mismatch", kind="mistake"),
        ]
    )

    tags = [line.split("]")[0] for line in text.splitlines()[1:]]
    assert tags == ["[mismatch - mistake", "[absent", "[unchecked", "[match"]


def test_a_line_names_the_claim_both_places_the_quote_and_the_note():
    text = checks_text([finding("mismatch", kind="choice")])

    line = text.splitlines()[1]
    assert line == (
        '[mismatch - choice] A says "the time step is 0.01 s" '
        '([paper.md · 4 Setup]). B ([solver.py · lines 1-3]): "dt = 0.05". '
        "B uses a bigger step"
    )


def test_an_absent_claim_has_no_place_in_b_and_no_quote():
    line = checks_text([finding("absent", quote="", note="not found")]).splitlines()[1]

    assert line == (
        '[absent] A says "the time step is 0.01 s" ([paper.md · 4 Setup]). not found'
    )


def test_a_long_line_is_cut_at_the_limit():
    line = checks_text([finding("mismatch", kind="choice", note="x" * 900)])
    line = line.splitlines()[1]

    assert len(line) == CHECK_LINE_CHARS
    assert line.endswith("…")


def test_no_findings_make_no_block_and_no_change_to_the_prompt():
    chunks = (chunk(0), chunk(1))

    assert checks_text([]) == ""
    assert build_answer_prompt(
        chunks, question="why?", files=2, findings=()
    ) == build_answer_prompt(chunks, question="why?", files=2)


def test_the_findings_sit_in_the_prompt_before_the_question():
    chunks = (chunk(0), chunk(1))

    prompt, _ = build_answer_prompt(
        chunks, question="why?", files=2, findings=[finding("mismatch", kind="choice")]
    )

    assert PRIOR_HEADING in prompt and CHECKS_NOTE in prompt
    assert prompt.index(CHECKS_NOTE) < prompt.index("QUESTION: why?")
    assert prompt.index("word word") < prompt.index(PRIOR_HEADING)


def test_with_no_file_there_is_nothing_to_check_and_the_findings_are_ignored():
    prompt, selected = build_answer_prompt(
        (), question="hi", files=0, findings=[finding("match")]
    )

    assert CHECKS_NOTE not in prompt
    assert selected == ()


def test_twenty_findings_never_push_the_prompt_over_the_budget():
    bare = 0
    while True:
        chunks = tuple(chunk(index) for index in range(bare + 1))
        prompt, _ = build_answer_prompt(chunks, question="why?", files=2)
        if estimate_tokens(prompt) > PROMPT_BUDGET - 600:
            break
        bare += 1
    chunks = tuple(chunk(index) for index in range(bare))
    many = [finding("mismatch", kind="choice", note="x" * 400) for _ in range(20)]

    prompt, selected = build_answer_prompt(chunks, question="why?", files=2)
    assert selected == chunks

    prompt, selected = build_answer_prompt(
        chunks, question="why?", files=2, findings=many
    )

    assert estimate_tokens(prompt) <= PROMPT_BUDGET
    assert len(selected) < len(chunks)
    assert prompt.count("[mismatch - choice]") == 20
