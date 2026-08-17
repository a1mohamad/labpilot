from __future__ import annotations

from labpilot.api import ApiConfig
from tests.api.conftest import COMPARE, QUESTION, problem


def test_root_names_the_service_and_where_its_docs_are(client):
    body = client.get("/").json()

    assert body["name"] == ApiConfig.TITLE
    assert body["version"] == ApiConfig.VERSION
    assert body["docs"] == "/docs"


def test_health_reports_how_many_tiers_are_usable(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["providers_configured"] >= 1


def test_health_does_not_spend_a_provider_request(client, fake):
    client.get("/health")

    assert fake.prompts == [], "a health check that costs quota gets switched off"


def test_a_body_over_the_whole_request_limit_is_refused_before_parsing(client):
    # A literal, never derived from the constant under test: a payload sized
    # from MAX_REQUEST_BODY_BYTES grows with it and the assertion can never fail.
    over = b"x" * 3_000_000
    assert over and len(over) > ApiConfig.MAX_REQUEST_BODY_BYTES, "must exceed it"

    response = client.post(
        COMPARE,
        files={
            "a": ("a.md", b"# hi\n\ntext", "text/markdown"),
            "b": ("b.py", over, "text/x-python"),
        },
        data={"question": QUESTION},
    )

    assert response.status_code == 413
    assert problem(response)["code"] == "request_too_large"
    assert response.headers["x-request-id"]


def test_a_successful_response_also_carries_a_request_id(client):
    assert client.get("/health").headers["x-request-id"]


def test_an_unknown_path_is_still_a_404(client):
    assert client.get("/nope").status_code == 404
