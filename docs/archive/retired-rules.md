# Retired rules

[Docs home](../README.md)

## Working Rules (Read First)

### Two files, one truth — CLAUDE.md and DETAILS.md

*Rule added 2026-10-11, at the user's request, after a whole session of notes
(section 20) reached CLAUDE.md and never reached DETAILS.md.*

**Every change to CLAUDE.md is made to DETAILS.md too, in the same session and
in the same commit.** A new section, a new bullet, a corrected sentence, a
changed status line: all of it, with the same words. DETAILS.md is the full
text, so it never holds LESS than CLAUDE.md and may hold more.

- CLAUDE.md may be compacted later. DETAILS.md is never compacted, and what a
  compaction removes from CLAUDE.md stays in DETAILS.md.
- DETAILS.md is laid out a little differently (it has no "Where Step 2 stands"
  block; it has the old banner and the tables of section 17.8). Put the same
  fact in its equivalent place.
- **Check before every docs commit:** `git diff --stat` must name BOTH files. If
  it names only one, the commit is not ready. Write in the commit message that
  both were updated.
- Claude does this without being asked, every time.
