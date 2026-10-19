"""CLAUDE.md and DETAILS.md must not drift apart.

The rule (Working Rules, "Two files, one truth"): every change to CLAUDE.md is
made to DETAILS.md too, in the same commit. It was broken on 2026-10-11, when a
whole session of notes reached CLAUDE.md and never reached DETAILS.md, and it
was found by hand. DETAILS.md is the full text and is laid out a little
differently, so only SECTION HEADINGS are compared, which is enough to catch a
new section that went into one file and not the other.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Blocks that exist only in the compact file, because DETAILS.md keeps the same
# facts in its older layout. A heading is excused by its START, since several
# carry a date that changes. A new name here needs a reason.
ONLY_IN_THE_COMPACT_FILE = (
    "### Where Step 2 stands",
    "### Traps that still bite",
    "### Git state and branches",
    "### Older status notes",
    "#### What step 3 builds",
)


def headings(name: str) -> list[str]:
    found: list[str] = []
    in_code = False
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"^#{2,4} ", line):
            found.append(line.strip())
    return found


def test_details_holds_every_section_heading_of_claude_md():
    in_details = set(headings("DETAILS.md"))

    missing = [
        heading
        for heading in headings("CLAUDE.md")
        if heading not in in_details
        and not heading.startswith(ONLY_IN_THE_COMPACT_FILE)
    ]

    assert not missing, (
        f"{missing} are in CLAUDE.md and not in DETAILS.md. Make every change to "
        f"both files, with the same words, in the same commit."
    )


def test_the_compact_file_blocks_that_are_excused_still_exist():
    # an excuse for a heading that is gone would hide the next real gap
    present = headings("CLAUDE.md")

    for start in ONLY_IN_THE_COMPACT_FILE:
        assert any(heading.startswith(start) for heading in present), (
            f"{start!r} is excused above and CLAUDE.md has no such heading now"
        )
