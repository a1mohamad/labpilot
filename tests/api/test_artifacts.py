from __future__ import annotations

import pytest
from fastapi import status

from labpilot.api.contracts import Ingested
from labpilot.store import ConnectionFailed, NotConfigured
from labpilot.store.contracts import ArtifactRecord

CODE = b"CLIP_NORM = 1.5\n\n\ndef train():\n    return CLIP_NORM\n"


def stored(minutes: float) -> Ingested:
    return Ingested(
        artifact=ArtifactRecord(
            id="B-abc",
            name="train.py",
            side="B",
            embedding_model="fake-embed",
            dim=3,
        ),
        chunks=7,
        embedding_minutes=minutes,
    )


@pytest.fixture
def no_database(monkeypatch):
    """Nothing here should open a real connection or call a provider."""
    import contextlib

    monkeypatch.setattr(
        "labpilot.api.routers.artifacts.connect",
        lambda *a, **k: contextlib.nullcontext(object()),
    )


def test_a_file_is_stored_and_its_id_comes_back(client, no_database, monkeypatch):
    monkeypatch.setattr(
        "labpilot.api.services.ingest_artifact", lambda *a, **k: stored(0.4)
    )

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("train.py", CODE, "text/x-python")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["artifact_id"] == "B-abc"
    assert body["chunks"] == 7
    assert body["embedding_model"] == "fake-embed"
    assert body["slow"] is False


def test_a_long_ingest_is_flagged_but_still_done(client, no_database, monkeypatch):
    """`slow` is a WARNING, not a refusal.

    The endpoint never waits for a human - an HTTP handler that blocks on a
    person is one that times out. It reports, and the UI decides.
    """
    monkeypatch.setattr(
        "labpilot.api.services.ingest_artifact", lambda *a, **k: stored(37.0)
    )

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("train.py", CODE, "text/x-python")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["slow"] is True


@pytest.mark.parametrize("failure", [NotConfigured, ConnectionFailed])
def test_an_unreachable_database_is_our_fault_not_the_users(
    client, monkeypatch, failure
):
    """503, never 422. The user's file was fine; our storage is not.

    This is the boundary the slice 4 review predicted three times: an
    unmapped store error would reach the 500 handler and blame the upload.
    """

    def explode(*args, **kwargs):
        raise failure("no database here")

    monkeypatch.setattr("labpilot.api.routers.artifacts.connect", explode)

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("train.py", CODE, "text/x-python")},
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error"]["code"] == "storage_unavailable"


def test_a_secret_file_is_refused_at_this_door_too(client, no_database):
    """The allowlist protects the door that READS it. Slice 3 found .env
    refused by the repository walk and accepted by the upload endpoint."""
    response = client.post(
        "/api/v1/artifacts",
        data={"side": "A"},
        files={"file": ("prod.env", b"KEY=secret", "text/plain")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "secret_upload"


def test_a_file_with_no_extension_is_refused(client, no_database):
    """The extension chooses the loader and the splitter. No extension means
    a silent downgrade, and a silent downgrade is worse than a rejection."""
    response = client.post(
        "/api/v1/artifacts",
        data={"side": "A"},
        files={"file": ("README", b"hello", "text/plain")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
