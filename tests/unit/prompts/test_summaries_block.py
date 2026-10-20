from labpilot.ingest import Chunk
from labpilot.prompts import REPORT, build_prompt, reserve
from labpilot.prompts.builder import PRIOR_HEADING, SUMMARIES_NOTE
from labpilot.tokens import estimate_tokens

CHUNKS = (
    Chunk(
        text="loss = bce(out, y)",
        source="b.py",
        start_line=1,
        end_line=1,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
    ),
)
SUMMARIES = {"A": "A is a paper about duplicates.", "B": "B trains an LSTM."}


def prompt(summaries):
    return build_prompt(
        CHUNKS, CHUNKS, question="why?", instructions=REPORT, summaries=summaries
    )


def test_each_summary_gets_its_own_heading_and_one_note_comes_before_them():
    text = prompt(SUMMARIES)

    assert text.count(SUMMARIES_NOTE) == 1
    assert "SUMMARY OF SIDE A\n\nA is a paper about duplicates." in text
    assert "SUMMARY OF SIDE B\n\nB trains an LSTM." in text
    assert text.index(SUMMARIES_NOTE) < text.index("SUMMARY OF SIDE A")


def test_the_summaries_sit_between_the_instructions_and_the_parts():
    text = prompt(SUMMARIES)

    assert text.index(REPORT.header) < text.index("SUMMARY OF SIDE A")
    assert text.index("SUMMARY OF SIDE B") < text.index("loss = bce(out, y)")


def test_a_blank_summary_is_left_out():
    text = prompt({"A": "   ", "B": "B trains an LSTM."})

    assert "SUMMARY OF SIDE A" not in text
    assert "SUMMARY OF SIDE B" in text


def test_no_summaries_leaves_the_prompt_as_it_was():
    plain = build_prompt(CHUNKS, CHUNKS, question="why?", instructions=REPORT)

    assert prompt(None) == plain
    assert prompt({}) == plain
    assert prompt({"A": "", "B": " "}) == plain


def test_the_reserve_counts_the_summaries():
    without = reserve(CHUNKS, question="why?", instructions=REPORT)
    with_summaries = reserve(
        CHUNKS, question="why?", instructions=REPORT, summaries=SUMMARIES
    )

    assert with_summaries - without >= estimate_tokens(SUMMARIES["A"])


def test_the_summaries_follow_the_order_of_the_sides_and_not_of_the_dict():
    text = prompt({"B": "B trains an LSTM.", "A": "A is a paper."})

    assert text.index("SUMMARY OF SIDE A") < text.index("SUMMARY OF SIDE B")


def test_a_summary_is_trimmed_before_it_is_written():
    text = prompt({"A": "\n  A is a paper.  \n\n"})

    assert "SUMMARY OF SIDE A\n\nA is a paper." in text


def test_the_findings_of_an_earlier_pass_still_come_after_the_parts():
    text = build_prompt(
        CHUNKS,
        CHUNKS,
        question="why?",
        instructions=REPORT,
        prior="a finding",
        summaries=SUMMARIES,
    )

    assert text.index("SUMMARY OF SIDE B") < text.index("loss = bce(out, y)")
    assert text.index("loss = bce(out, y)") < text.index(PRIOR_HEADING)
