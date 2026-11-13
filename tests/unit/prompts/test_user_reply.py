from labpilot.prompts import USER_REPLY_NOTE, question_with_reply


def test_no_reply_leaves_the_question_exactly_as_it_was():
    assert question_with_reply("why lower?", "") == "why lower?"
    assert question_with_reply("why lower?", "   ") == "why lower?"


def test_a_reply_comes_after_the_question_behind_a_note_that_says_whose_it_is():
    out = question_with_reply("why lower?", "Asked: What F1?\nAnswer: 0.82")

    assert out.startswith("why lower?")
    assert USER_REPLY_NOTE in out
    assert out.endswith("Asked: What F1?\nAnswer: 0.82")
    assert out.index(USER_REPLY_NOTE) < out.index("Answer: 0.82")


def test_the_note_says_the_words_are_not_evidence_from_the_files():
    assert "not from the files" in USER_REPLY_NOTE
    assert "you said" in USER_REPLY_NOTE
