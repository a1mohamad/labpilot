from __future__ import annotations

import contextlib
import io
import zipfile

import pytest
from fastapi import status

from labpilot.api import ApiConfig
from labpilot.api.contracts import Ingested
from labpilot.sources import (
    CloneFailed,
    Source,
    SourceNotFound,
    SourceTooLarge,
    UnsafeArchive,
    UnsupportedURL,
)
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
        ingest_minutes=minutes,
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


# --- the repository door: one of three inputs, then one shared store path ----


def zip_bytes(files: dict[str, str]) -> bytes:
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        for relpath, text in files.items():
            archive.writestr(relpath, text)
    return raw.getvalue()


@pytest.fixture
def opened(monkeypatch):
    """Capture the Source that reached the store, without storing anything.

    The door's whole job is CHOOSING an opener, so what has to be observed is
    which one ran and what it produced - not the write path, which the
    ingest_source integration tests cover against a real database.
    """
    seen: list[tuple[str, set[str], str]] = []

    def fake_ingest_source(conn, source, *, side):
        # Read the folder HERE, not in the test. open_zip and open_git both
        # delete their temporary directory on the way out, so by the time an
        # assertion runs, source.root is gone and every listing is empty.
        files = {path.name for path in source.root.rglob("*") if path.is_file()}
        seen.append((source.name, files, side))
        return stored(0.2)

    monkeypatch.setattr("labpilot.api.services.ingest_source", fake_ingest_source)
    return seen


@pytest.fixture
def never_a_single_file(monkeypatch):
    """ingest_artifact is the OTHER branch. It must not run for an archive."""

    def refuse(*args, **kwargs):
        raise AssertionError("the single-file path ran for an archive")

    monkeypatch.setattr("labpilot.api.services.ingest_artifact", refuse)


def test_a_zip_is_unpacked_and_stored_as_one_artifact(
    client, no_database, opened, never_a_single_file
):
    """A real archive through the real opener - only the store is faked.

    Uploading a repository must not be read as ONE file. On the single-file
    path a zip is binary, so it would die at the door as 'not UTF-8 text' and
    the repository door would silently never have worked at all.
    """
    raw = zip_bytes({"src/train.py": "lr = 3e-4\n", "README.md": "# Title\n"})

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("my-repo.zip", raw, "application/zip")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    ((name, unpacked, side),) = opened
    assert unpacked == {"train.py", "README.md"}
    assert side == "B", "the side on the form must reach the store"
    assert name == "my-repo"


def test_an_archive_is_recognised_whatever_the_case_of_its_suffix(
    client, no_database, opened, never_a_single_file
):
    """The branch folds case, and Windows really does hand over REPO.ZIP.

    Without the fold it takes the single-file path, where a zip is binary and
    is refused as 'not UTF-8 text' - a confusing 422 for an upload the door
    does in fact support.
    """
    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("REPO.ZIP", zip_bytes({"a.py": "x = 1\n"}), "application/zip")},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert len(opened) == 1


def test_an_ordinary_file_never_takes_the_archive_path(
    client, no_database, opened, monkeypatch
):
    """The mirror of the two tests above: one file is ONE file."""
    monkeypatch.setattr(
        "labpilot.api.services.ingest_artifact", lambda *a, **k: stored(0.1)
    )

    assert upload(client, "train.py", CODE).status_code == status.HTTP_201_CREATED
    assert opened == [], "a .py must not be opened as a repository"


def test_a_git_url_is_cloned_and_stored_as_one_artifact(
    client, no_database, opened, monkeypatch, tmp_path
):
    """No file crosses the wire at all - the URL is the whole request."""
    (tmp_path / "train.py").write_text("lr = 3e-4\n", encoding="utf-8")
    cloned = []

    @contextlib.contextmanager
    def fake_open_git(url: str):
        cloned.append(url)
        yield Source(name="labpilot", root=tmp_path)

    monkeypatch.setattr("labpilot.api.routers.artifacts.open_git", fake_open_git)

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B", "url": "https://github.com/a1mohamad/labpilot"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert cloned == ["https://github.com/a1mohamad/labpilot"]
    assert [name for name, _, _ in opened] == ["labpilot"]


@pytest.mark.parametrize(
    "sent",
    [
        pytest.param({"side": "B"}, id="neither"),
        pytest.param(
            {"side": "B", "url": "https://github.com/a1mohamad/labpilot"}, id="both"
        ),
    ],
)
def test_exactly_one_of_a_file_and_a_url_is_required(client, no_database, sent):
    """Neither is nothing to ingest. BOTH is worse than nothing: the door
    would quietly honour one and drop the other, and the user would be told
    their upload was stored when a different artifact was."""
    files = {"file": ("train.py", CODE, "text/x-python")} if "url" in sent else None

    response = client.post("/api/v1/artifacts", data=sent, files=files)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "unreadable_source"


def test_a_repository_over_the_limit_is_a_413_that_names_the_size(
    client, no_database, monkeypatch
):
    """Refuse, never truncate. Half a corpus searched silently returns
    confident wrong answers, which is worse than a rejection - and 413 is the
    same class as an oversized upload, because the cause is the same."""

    def too_big(conn, source, *, side):
        raise SourceTooLarge("repo is 41000000 bytes, over the 20000000 limit")

    monkeypatch.setattr("labpilot.api.services.ingest_source", too_big)

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("big.zip", zip_bytes({"a.py": "x = 1\n"}), "application/zip")},
    )

    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    body = response.json()["error"]
    assert body["code"] == "source_too_large"
    assert "20000000" in body["message"]


def test_a_zip_bomb_is_a_422_and_not_a_500(client, no_database, monkeypatch):
    """UnsafeArchive is raised by open_zip, which runs INSIDE the route's try.

    Unmapped it reaches the 500 handler and reads as our bug rather than as a
    hostile upload - the boundary failure this project has now hit three
    times, each with a new error type crossing an older except clause.
    """

    @contextlib.contextmanager
    def bomb(path):
        raise UnsafeArchive("declares 200000000 bytes, over the limit")
        yield  # pragma: no cover - unreachable, and required to be a manager

    monkeypatch.setattr("labpilot.api.routers.artifacts.open_zip", bomb)

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B"},
        files={"file": ("bomb.zip", zip_bytes({"a.py": "x = 1\n"}), "application/zip")},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["error"]["code"] == "unsafe_archive"


@pytest.mark.parametrize("failure", [CloneFailed, SourceNotFound, UnsupportedURL])
def test_every_way_a_source_will_not_open_is_the_callers_fault(
    client, no_database, monkeypatch, failure
):
    """422 for all three: a URL we refuse, a clone that failed, a path that is
    not there. Each is a fact about the REQUEST and each is fixable by the
    caller, so none of them may be reported as a server error."""

    @contextlib.contextmanager
    def refuse(url):
        raise failure("git said no")
        yield  # pragma: no cover - unreachable, and required to be a manager

    monkeypatch.setattr("labpilot.api.routers.artifacts.open_git", refuse)

    response = client.post(
        "/api/v1/artifacts",
        data={"side": "B", "url": "https://github.com/a1mohamad/labpilot"},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    body = response.json()["error"]
    assert body["code"] == "unreadable_source"
    assert "git said no" in body["message"]
