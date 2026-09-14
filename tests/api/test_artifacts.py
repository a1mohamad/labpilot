from __future__ import annotations

import pytest
from fastapi import status

from labpilot.api import ApiConfig
from labpilot.api.contracts import Ingested
from labpilot.store import ConnectionFailed, NotConfigured
from labpilot.store.contracts import ArtifactRecord
from tests.api.conftest import SAMPLES
from tests.unit.ingest.test_pdf import a_pdf_with_no_text_layer

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


def upload(client, name: str, raw: bytes, kind: str = "text/x-python", side: str = "B"):
    """One upload, at the door that now owns every upload.

    The tests below moved here from test_compare.py on 2026-09-14, when
    /compare stopped taking files. They were never really about comparing:
    read_artifact is the guard, it is SHARED by both routes, and testing it
    through /compare once /artifacts existed was one test per COMBINATION
    rather than one per failure.
    """
    return client.post(
        "/api/v1/artifacts", data={"side": side}, files={"file": (name, raw, kind)}
    )


def test_a_binary_upload_is_rejected_as_not_text(client, no_database):
    """Refuse what cannot be handled well. A silent downgrade is worse than a
    rejection, because nobody ever learns it happened."""
    response = upload(client, "logo.png", b"\x89PNG\r\n\x1a\n\x00\x00", "image/png")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unreadable_upload"
    assert "not UTF-8" in response.json()["error"]["message"]


def test_an_upload_over_the_size_limit_is_rejected(client, no_database):
    """A LITERAL payload, never one derived from the constant under test.

    The first version of this computed its size from MAX_UPLOAD_BYTES, so
    raising the limit grew the payload with it and the assertion could never
    fail. It was green for three runs while testing nothing.
    """
    huge = b"x = 1\n" * 900_000
    assert len(huge) > ApiConfig.MAX_UPLOAD_BYTES, "must exceed the real limit"

    response = upload(client, "big.py", huge)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"


def test_an_upload_under_the_size_limit_is_accepted(client, no_database, monkeypatch):
    """The other half, so the limit cannot silently drift down to zero."""
    monkeypatch.setattr(
        "labpilot.api.services.ingest_artifact", lambda *a, **k: stored(0.1)
    )
    ordinary = b"x = 1\n" * 100_000
    assert len(ordinary) < ApiConfig.MAX_UPLOAD_BYTES

    assert upload(client, "ordinary.py", ordinary).status_code == 201


def test_an_empty_upload_is_rejected(client, no_database):
    """An artifact with no text yields no chunks, and a corpus of nothing
    answers every question with silence."""
    response = upload(client, "empty.py", b"")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_artifact"


def test_a_pdf_is_read_as_a_document_not_refused_as_binary(
    client, no_database, monkeypatch
):
    """Papers are PDFs. The door must not decode before the loader runs -
    that is the whole reason LOADERS takes bytes rather than str."""
    monkeypatch.setattr(
        "labpilot.api.services.ingest_artifact", lambda *a, **k: stored(0.1)
    )
    pdf = (SAMPLES.parent / "pdf" / "one_column.pdf").read_bytes()

    response = upload(client, "paper.pdf", pdf, "application/pdf", side="A")

    assert response.status_code == 201


def test_a_scanned_pdf_is_a_422_that_says_why(client, no_database):
    """A scan has no text layer at all, so extraction SUCCEEDS and returns "".

    The silent failure in its purest form - nothing raises, and the model
    would be asked about an empty file.
    """
    response = upload(
        client, "scan.pdf", a_pdf_with_no_text_layer(), "application/pdf", side="A"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unreadable_upload"


def test_non_ascii_content_survives_the_door(client, no_database, monkeypatch):
    """Hit for real on 2026-08-17 outside the app, printing a U+2212 minus."""
    seen = {}

    def fake_ingest(conn, raw, *, name, side, field="artifact"):
        seen["raw"] = raw
        return stored(0.1)

    monkeypatch.setattr("labpilot.api.services.ingest_artifact", fake_ingest)
    body = "ratio = 0.5  # −4.1 F1, α ≤ 0.05".encode()

    upload(client, "odd.py", body)

    assert seen["raw"] == body, "the door must not transcode what it passes on"


def test_a_broken_notebook_is_a_422_not_a_500(client, no_database):
    """LoaderError is not an ApiError, so without the guard in services._cut a
    malformed .ipynb reaches the 500 handler and reads as OUR bug rather than
    the user's file. Reachable only since .ipynb became an accepted upload.

    Moved from test_compare.py on 2026-09-14 with the rest of the upload door.
    """
    response = upload(client, "run.ipynb", b"{not json at all", "application/json")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "unreadable_upload"
    assert "run.ipynb" in body["message"]
