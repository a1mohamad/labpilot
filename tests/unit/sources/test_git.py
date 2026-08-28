from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from labpilot.sources import walk
from labpilot.sources.defaults import CLONE_TIMEOUT_SECONDS
from labpilot.sources.errors import CloneFailed, UnsupportedURL
from labpilot.sources.git import _repository_name, _validated, open_git

REPO = "https://github.com/a1mohamad/labpilot"


@pytest.fixture
def recorded(monkeypatch):
    calls: list[dict] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        root = Path(command[-1])
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "src" / "train.py").write_text("x = 1", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("labpilot.sources.git.subprocess.run", fake_run)
    return calls


@pytest.mark.parametrize(
    "url",
    [
        "ext::sh -c 'rm -rf /'",
        "http://github.com/a/b",
        "git@github.com:a/b.git",
        "file:///etc/passwd",
        "ssh://git@github.com/a/b",
        "https://user:secret@github.com/a/b",
        "https:///no-host",
        "",
    ],
)
def test_only_an_https_address_is_accepted(url):
    with pytest.raises(UnsupportedURL):
        _validated(url)


def test_a_plain_https_address_is_accepted():
    assert _validated(f"  {REPO}  ") == REPO


def test_a_refused_address_never_reaches_git(recorded):
    with pytest.raises(UnsupportedURL):
        with open_git("ext::sh -c 'cat .env'"):
            pass

    assert recorded == []


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{REPO}.git", "labpilot"),
        (REPO, "labpilot"),
        ("https://github.com/", "repository"),
    ],
)
def test_the_repository_name_comes_from_the_address(url, expected):
    assert _repository_name(url) == expected


def test_a_clone_is_shallow_and_passes_the_url_as_one_argument(recorded):
    with open_git(REPO) as source:
        root = str(source.root)

    command = recorded[0]["command"]

    assert command[:2] == ["git", "clone"]
    assert "--depth" in command and command[command.index("--depth") + 1] == "1"
    assert "--single-branch" in command
    assert command[-3:] == ["--", REPO, root]


def test_a_clone_never_goes_through_a_shell(recorded):
    with open_git(REPO):
        pass

    assert recorded[0].get("shell", False) is False
    assert isinstance(recorded[0]["command"], list)


def test_git_is_told_not_to_ask_for_a_password(recorded):
    with open_git(REPO):
        pass

    assert recorded[0]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert recorded[0]["timeout"] == CLONE_TIMEOUT_SECONDS


def test_a_cloned_repository_becomes_a_walkable_source(recorded):
    with open_git(REPO) as source:
        assert source.name == "labpilot"
        assert [f.relpath for f in walk(source)] == ["src/train.py"]


def test_the_clone_is_deleted_afterwards(recorded):
    with open_git(REPO) as source:
        root = source.root
        assert root.exists()

    assert not root.exists()


def test_the_clone_is_deleted_even_when_the_body_raises(recorded):
    root = None

    with pytest.raises(RuntimeError):
        with open_git(REPO) as source:
            root = source.root
            raise RuntimeError("the caller exploded")

    assert root is not None
    assert not root.exists()


def test_gits_own_message_survives_a_failed_clone(monkeypatch):
    def failing_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 128, "", "fatal: repo not found")

    monkeypatch.setattr("labpilot.sources.git.subprocess.run", failing_run)

    with pytest.raises(CloneFailed, match="fatal: repo not found"):
        with open_git(REPO):
            pass


def test_a_missing_git_binary_is_reported_plainly(monkeypatch):
    def no_git(command, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr("labpilot.sources.git.subprocess.run", no_git)

    with pytest.raises(CloneFailed, match="git is not installed"):
        with open_git(REPO):
            pass


def test_a_slow_clone_is_given_up_on(monkeypatch):
    def hanging_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, CLONE_TIMEOUT_SECONDS)

    monkeypatch.setattr("labpilot.sources.git.subprocess.run", hanging_run)

    with pytest.raises(CloneFailed, match="took longer than"):
        with open_git(REPO):
            pass
