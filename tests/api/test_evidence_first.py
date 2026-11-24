"""R20: the code a finding is about is kept when the search hits are cut."""

from labpilot.api.headers import RAW_REQUEST_ID_HEADER, REQUEST_ID_HEADER
from labpilot.api.prompting import build_answer_prompt
from labpilot.ingest import Chunk


def part(side, index, words):
    return Chunk(
        text="word " * words,
        source="train.py",
        start_line=1,
        end_line=2,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
    )


# 40 parts of about 2,000 tokens: far over the prompt's budget.
HITS = tuple(part("B", n, 1_200) for n in range(100, 140))
TOTALS = {"B": 500}


def ask(evidence):
    return build_answer_prompt(
        HITS, question="why?", files=1, totals=TOTALS, evidence=evidence
    )


def ids(chunks):
    return [chunk.chunk_index for chunk in chunks]


def test_the_last_hit_is_cut_when_nothing_was_found_in_it():
    _, selected = ask(())

    assert 139 not in ids(selected)


def test_a_hit_that_a_finding_is_about_is_sent_first():
    _, selected = ask((HITS[-1],))

    assert 139 in ids(selected)


def test_a_part_the_search_missed_is_sent_when_a_finding_is_about_it():
    _, selected = ask((part("B", 7, 1_200),))

    assert 7 in ids(selected)


def test_the_raw_header_is_the_same_name_in_lower_case():
    # ASGI compares the raw names as bytes, so one capital letter would add the
    # request id a second time.
    assert RAW_REQUEST_ID_HEADER == b"x-request-id"
    assert REQUEST_ID_HEADER.lower().encode() == RAW_REQUEST_ID_HEADER
