import pytest

from labpilot.api import reading
from labpilot.api.errors import ArtifactSidesClash
from labpilot.prompts import Instructions
from labpilot.store import ArtifactRecord, StoredArtifact


def stored(artifact_id, side):
    return StoredArtifact(
        artifact=ArtifactRecord(
            id=artifact_id, name="m.py", side=side, embedding_model="m", dim=3
        ),
        chunks=2,
        characters=100,
    )


@pytest.fixture
def measured(monkeypatch):
    asked = []

    def fake_measure(conn, artifact_id):
        asked.append(artifact_id)
        return stored(artifact_id, artifact_id[0])

    monkeypatch.setattr(reading, "measure", fake_measure)
    return asked


def test_an_empty_id_is_skipped_and_the_other_side_is_measured(measured):
    found = reading.measure_sides(object(), "", "B-1")

    assert list(found) == ["B"]
    assert measured == ["B-1"]


def test_two_empty_ids_measure_nothing(measured):
    assert reading.measure_sides(object(), "", "") == {}
    assert measured == []


def test_two_ids_of_the_same_side_are_still_refused(measured):
    with pytest.raises(ArtifactSidesClash):
        reading.measure_sides(object(), "A-1", "A-2")


def test_nothing_to_read_always_fits():
    assert reading.fits_whole({}, question="hi") is True


def test_the_fixed_cost_comes_from_the_instruction_for_that_many_files(monkeypatch):
    asked = []

    def fake_instructions_for(files):
        asked.append(files)
        return Instructions("big", "h" * 100_000, "")

    monkeypatch.setattr(reading, "instructions_for", fake_instructions_for)

    assert reading.fits_whole({}, question="hi") is False
    assert asked == [0]


def test_two_artifacts_are_charged_for_the_two_file_instruction(monkeypatch):
    asked = []

    def fake_instructions_for(files):
        asked.append(files)
        return Instructions("small", "h", "")

    monkeypatch.setattr(reading, "instructions_for", fake_instructions_for)
    sides = {"A": stored("A-1", "A"), "B": stored("B-1", "B")}

    assert reading.fits_whole(sides, question="hi") is True
    assert asked == [2]
