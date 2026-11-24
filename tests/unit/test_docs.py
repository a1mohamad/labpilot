"""The docs folder is one truth, every link in it works, and CLAUDE.md stays small.

CLAUDE.md is loaded at the start of every session. It grew to 1.4 MB, next to a
DETAILS.md of 1.6 MB that had to hold the same words, until 2026-11-24. Now it is a
short front page and the text lives in docs/, each fact on one page.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from scripts.repo import build_docs_index as index

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / "CLAUDE.md"
MAX_CLAUDE_BYTES = 16_000
PAGES = [CLAUDE, *sorted((ROOT / "docs").rglob("*.md"))]
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    for heading in index.headings(path):
        name, n = index.slug(heading), 1
        unique = name
        while unique in found:
            unique, n = f"{name}-{n}", n + 1
        found.add(unique)
    return found


def prose(path: Path) -> str:
    """The text without fenced code and code spans (they show links as examples)."""
    text = re.sub(
        r"^(```|~~~).*?^\1", "", path.read_text(encoding="utf-8"), flags=re.M | re.S
    )
    return re.sub(r"`[^`\n]*`", "", text)


def test_claude_md_stays_small_enough_to_load_in_every_session():
    assert CLAUDE.stat().st_size <= MAX_CLAUDE_BYTES, (
        "CLAUDE.md is the front page. Put the text in a page of docs/ and link it."
    )


def test_there_is_no_second_copy_of_the_docs():
    assert not (ROOT / "DETAILS.md").exists()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_link_to_a_file_or_a_heading_works(page):
    broken = []
    for target in LINK.findall(prose(page)):
        if re.match(r"[a-z]+:", target):
            continue  # a web address
        file, _, anchor = target.partition("#")
        path = (page.parent / file).resolve() if file else page
        if not path.exists():
            broken.append(target)
        elif anchor and path.suffix == ".md" and anchor not in anchors(path):
            broken.append(target)

    assert not broken, f"{page.name} links to {broken}"


def test_the_generated_pages_are_up_to_date():
    for name, text in index.generated().items():
        written = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert written == text, f"run python -m scripts.repo.build_docs_index ({name})"
    tree = (ROOT / "docs" / "SUMMARY.md").read_text(encoding="utf-8")
    assert tree == index.summary(), "run python -m scripts.repo.build_docs_index"


def test_the_order_of_the_pages_is_the_same_on_windows_and_on_linux():
    names = ["docs/README.md", "docs/archive/a.md", "docs/Zoo.md", "docs/agent/b.md"]
    order = [*map(str, index.in_order(map(PurePosixPath, names)))]

    assert order == [p.as_posix() for p in index.in_order(map(PureWindowsPath, names))]
    assert order == sorted(names)


def test_every_folder_of_docs_is_in_the_tree():
    folders = {p.name for p in (ROOT / "docs").iterdir() if p.is_dir()}

    assert folders <= {name for name, _ in index.FOLDERS}


def test_the_pages_every_session_needs_are_linked_from_the_front_page():
    front = CLAUDE.read_text(encoding="utf-8")
    for needed in ("docs/README.md", "docs/status/current.md", "docs/rules/"):
        assert needed in front
