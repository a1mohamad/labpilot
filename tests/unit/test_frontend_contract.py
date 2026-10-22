"""THE PAGE READS FIELDS OFF OUR RESPONSES, AND NOTHING CHECKED THE NAMES.

This is the one drift in the project with two recorded incidents behind it.

    slice 7   `/compare` started taking IDS instead of files. `web/app.js` kept
              posting two files and got a 422 - the page was broken for a WEEK
              and the suite stayed green the whole time.
    2026-09-19  `embedding_minutes` was renamed `ingest_minutes` across
              contracts, schemas and the router. Had `app.js` been missed, the
              card would have rendered `~undefined min to ingest`.

Both are the same shape and neither is catchable by any test that stops at the
API boundary: Pydantic will happily rename a field, every api/ test updates with
it, and the only consumer that disagrees is a file written in another language
that nothing imports.

So this reads `web/app.js` as TEXT and checks the names against the models that
really produce them. It is the same move `test_packaging.py` makes for
requirements.txt and `.env.example` - a config-drift test, cheap, and it fires
on exactly the mistake that has happened twice.

WHAT IT DELIBERATELY DOES NOT DO: run the page, check layout, or check that a
field is USED correctly. A name is the part that breaks silently; everything
else about `web/` is Step 3's rewrite and is throwaway by design.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from labpilot.api.schemas import (
    CompareRequest,
    CompareResponse,
    ErrorEnvelope,
    IngestResponse,
)

APP_JS = Path("web/app.js")

# `payload.` is the ingest reply, `body.` the compare reply - the two names
# app.js gives them. Anything else it reads is a DOM node, not our wire format.
_READS = re.compile(r"\b(payload|body)\.([a-zA-Z_][a-zA-Z0-9_]*)")

# Names that are not fields of ours. `append` is FormData's; `hidden`,
# `textContent` and friends belong to the DOM.
_NOT_OURS = {"append", "hidden", "textContent", "dataset", "classList", "style"}


# The object literal inside `JSON.stringify({ ... })` of the compare request.
_COMPARE_BODY = re.compile(r"JSON\.stringify\(\{(?P<fields>.*?)\}\)", re.DOTALL)


def _sent_to_compare() -> set[str]:
    source = APP_JS.read_text(encoding="utf-8")
    after_fetch = source[source.index("fetch(COMPARE") :]
    body = _COMPARE_BODY.search(after_fetch)
    assert body, "app.js no longer builds the compare request as JSON.stringify({...})"
    return set(re.findall(r"^\s*(\w+)\s*[:,]", body.group("fields"), re.MULTILINE))


def _reads(prefix: str) -> set[str]:
    source = APP_JS.read_text(encoding="utf-8")
    return {
        field
        for seen, field in _READS.findall(source)
        if seen == prefix and field not in _NOT_OURS
    }


@pytest.mark.parametrize(
    ("prefix", "model"),
    [("payload", IngestResponse), ("body", CompareResponse)],
    ids=("ingest", "compare"),
)
def test_every_response_field_the_page_reads_is_one_we_really_send(prefix, model):
    # EITHER reply may arrive under the same name. `app.js` parses the JSON
    # once and branches on `response.ok`, so `payload.error.code` on the
    # failure branch is correct and not drift - the first draft of this test
    # reported it as a missing field, and the test was wrong, not the page.
    allowed = set(model.model_fields) | set(ErrorEnvelope.model_fields)
    missing = sorted(_reads(prefix) - allowed)

    assert not missing, (
        f"web/app.js reads {missing} off the {model.__name__} reply and we do "
        f"not send them. In a browser each one is `undefined` - no error, no "
        f"failed request, just a card rendering nothing. Rename the field in "
        f"app.js too, or put it back on the model."
    )


def test_the_page_is_really_wired_to_both_doors():
    """The premise of the two tests above, and without it they pass on nothing.

    If `app.js` is ever rewritten to read its data some other way - a helper, a
    destructured object - `_reads` returns an empty set and the checks above
    become vacuously true while the drift they exist to catch walks straight
    past. This is the parametrized-test trap that deleted
    `test_a_readable_suffix_with_no_loader_is_really_plain_text`: an assertion
    that cannot fail is not a test, however many times it runs.
    """
    assert _reads("payload"), (
        "app.js no longer reads any field off the ingest reply, so the ingest "
        "half of this file is checking nothing. Re-point the regex."
    )
    assert _reads("body"), (
        "app.js no longer reads any field off the compare reply, so the "
        "compare half of this file is checking nothing. Re-point the regex."
    )


def test_the_page_sends_every_field_of_the_compare_request():
    """Without the chat id every message starts a NEW chat.

    Nothing fails when the page forgets it: the server accepts a request with no
    id, makes a fresh one, and answers normally. So the page looks perfectly
    healthy and the chat remembers nothing. Same family as the two incidents
    above - a name that is missing breaks silently.
    """
    sent = _sent_to_compare()

    assert sent, "the compare request holds no fields, so this test checks nothing"
    missing = sorted(set(CompareRequest.model_fields) - sent)
    assert not missing, (
        f"web/app.js does not send {missing} to /compare. Add it, or the server "
        f"never sees it."
    )


@pytest.mark.parametrize("side", ["A", "B"])
def test_the_page_never_reads_the_id_of_a_slot_that_may_be_empty(side):
    """With no side, one side or both stored, an empty slot must send null.

    `stored.A.artifact_id` on an empty slot throws, the click does nothing and
    no request goes out, so the page looks alive and cannot ask. Every read of
    an id has to sit behind a check of the slot, which is what the compare
    request does: `stored.A ? stored.A.artifact_id : null`.
    """
    source = APP_JS.read_text(encoding="utf-8")
    reads = source.count(f"stored.{side}.artifact_id")
    guarded = source.count(f"stored.{side} ? stored.{side}.artifact_id")

    assert reads, f"app.js no longer reads the id of side {side}; re-point this test"
    assert guarded == reads, (
        f"app.js reads stored.{side}.artifact_id {reads} times and guards it "
        f"{guarded}. An empty slot would throw."
    )


def test_the_request_takes_no_ids_one_id_or_two():
    assert CompareRequest(question="why?").a is None
    assert CompareRequest(question="why?", b="B-1").b == "B-1"
    assert CompareRequest(question="why?", a="A-1", b="B-1").a == "A-1"


def test_the_page_keeps_the_chat_id_the_server_sent():
    """The other half: the id arrives in the FIRST reply, and the page must read
    it or there is nothing to send with the second question."""
    assert "thread_id" in _reads("body"), (
        "web/app.js never reads thread_id off the compare reply, so it cannot "
        "send it back and every question starts a new chat."
    )
