from labpilot.api.prompting import build_report_prompt
from labpilot.ingest import Chunk

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


def test_the_report_prompt_carries_the_summaries():
    prompt, selected = build_report_prompt(
        CHUNKS, question="why?", summaries={"B": "B trains an LSTM."}
    )

    assert "B trains an LSTM." in prompt
    assert selected == CHUNKS


def test_the_report_prompt_is_the_same_without_summaries():
    prompt, _ = build_report_prompt(CHUNKS, question="why?")

    assert "SUMMARY OF SIDE" not in prompt
