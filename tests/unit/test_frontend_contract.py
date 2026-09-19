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

from labpilot.api.schemas import CompareResponse, ErrorEnvelope, IngestResponse

APP_JS = Path("web/app.js")

# `payload.` is the ingest reply, `body.` the compare reply - the two names
# app.js gives them. Anything else it reads is a DOM node, not our wire format.
_READS = re.compile(r"\b(payload|body)\.([a-zA-Z_][a-zA-Z0-9_]*)")

# Names that are not fields of ours. `append` is FormData's; `hidden`,
# `textContent` and friends belong to the DOM.
_NOT_OURS = {"append", "hidden", "textContent", "dataset", "classList", "style"}


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
