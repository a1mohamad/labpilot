from __future__ import annotations

import pytest

from labpilot.api import ApiConfig, app
from labpilot.api.errors import ApiError
from labpilot.api.schemas import ErrorEnvelope
from tests.api.conftest import COMPARE, QUESTION, post, problem

HTTP_CODES = range(400, 600)


def raisable() -> tuple[type[ApiError], ...]:
    found: dict[str, type[ApiError]] = {}
    stack = [ApiError]
    while stack:
        for sub in stack.pop().__subclasses__():
            found[sub.__name__] = sub
            stack.append(sub)

    return tuple(found.values())


def test_the_error_hierarchy_is_not_empty():
    """Every test below reads the hierarchy, so an empty one would make them
    all pass while checking nothing."""
    assert len(raisable()) >= 5


@pytest.mark.parametrize("failure", raisable(), ids=lambda cls: cls.__name__)
def test_every_error_declares_a_real_status_and_its_own_code(failure):
    assert failure.status in HTTP_CODES
    assert failure.code and failure.code == failure.code.lower()
    assert " " not in failure.code


def test_no_two_errors_share_a_code():
    """`code` is the machine-readable half of the envelope. Two classes sharing
    one makes them indistinguishable to a client, and copy-paste is how it
    happens."""
    codes = [failure.code for failure in raisable()]

    assert len(codes) == len(set(codes)), f"duplicate codes in {sorted(codes)}"


def test_every_status_the_endpoint_can_raise_is_documented():
    """Derived from the hierarchy, not hardcoded.

    The first version of this test asserted a fixed set with `<=`, so adding an
    ApiError with a new status would have left it green while OpenAPI lied
    about what the endpoint returns.
    """
    documented = set(
        app.openapi()["paths"][f"{ApiConfig.PREFIX}/compare"]["post"]["responses"]
    )
    raisable_statuses = {str(failure.status) for failure in raisable()}

    assert "200" in documented
    assert raisable_statuses <= documented, (
        f"undocumented: {sorted(raisable_statuses - documented)}"
    )


def test_an_application_error_matches_the_published_envelope(client):
    ErrorEnvelope.model_validate(post(client, question="   ").json())


def test_the_body_limit_middleware_speaks_the_same_envelope(client):
    """The middleware builds its JSON by hand, because it answers before the
    application and its handlers exist. That hand-built body is the one thing
    that can drift away from ErrorEnvelope without anything noticing."""
    over = b"x" * 11_000_000
    assert len(over) > ApiConfig.MAX_REQUEST_BODY_BYTES, "must exceed the ceiling"

    response = client.post(
        COMPARE,
        files={
            "a": ("a.md", b"# hi\n\ntext", "text/markdown"),
            "b": ("b.py", over, "text/x-python"),
        },
        data={"question": QUESTION},
    )

    assert response.status_code == 413
    ErrorEnvelope.model_validate(response.json())


def test_an_unexpected_exception_becomes_a_500_in_the_same_envelope(
    lenient_client, fake
):
    fake.error = RuntimeError("something nobody predicted")

    response = lenient_client.post(
        COMPARE,
        files={
            "a": ("a.md", b"# hi\n\ntext", "text/markdown"),
            "b": ("b.py", b"x = 1\n", "text/x-python"),
        },
        data={"question": QUESTION},
    )

    assert response.status_code == 500
    assert problem(response)["code"] == "internal_error"
    assert "something nobody predicted" not in response.text, "never leak internals"
    ErrorEnvelope.model_validate(response.json())


def test_a_broken_notebook_is_a_422_not_a_500(client):
    # LoaderError is not an ApiError, so without the guard in services._cut a
    # malformed .ipynb reaches the 500 handler and reads as our bug, not the
    # user's file. Reachable only since .ipynb became an accepted upload.
    response = client.post(
        "/api/v1/compare",
        files={
            "a": ("paper.md", b"# Title\n\nsome text\n", "text/markdown"),
            "b": ("run.ipynb", b"{not json at all", "application/json"),
        },
        data={"question": "compare these"},
    )

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "unreadable_upload"
    assert "run.ipynb" in body["message"]
