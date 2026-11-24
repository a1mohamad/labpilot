# Sessions, commits and the review pass

[Docs home](../README.md)

### Commit messages go in ONE file, and it is overwritten every time

*Rule added 2026-11-10, at the user's request, after Claude made a second file.*

When the user asks for commit messages, Claude REWRITES `artifacts/commit_messages.txt`
(one line for each file, `path|message`, the format `scripts/repo/merge_per_file.py --messages`
reads). The old content is not needed any more, so it is simply overwritten. Claude never
creates a new messages file (no `commit_messages_lesson4.txt` and the like).

### Review pass after every slice, and a hand-off prompt at the end of every session

*Two rules added 2026-10-21, at the user's request. Both are Claude's job, and both are done
without being asked.*

**1. After the last lesson of every slice, run a full review pass before the next slice
starts.** Look at the whole system from above, not only at the new files: Step 2 so far, the
slice, and the whole app. The standing question is the same as always: *which real failure is
still unprotected?* The steps:

- Read the code that joins the new slice to the rest: the wiring in `api/`, the state, the
  saver, the page contract.
- List the joins that no test crosses (a real database, the real saver, two threads at once, a
  provider that fails) and add the missing tests.
- Break one line for each new invariant test and read WHICH test fires (mutation testing; keep a
  copy of the file aside and restore from the copy, never with `git checkout`).
- Look for dead code and for scripts that still name removed functions.
- Run the whole suite (unit, api and integration, without `--run-smoke`) and fix what is red.
- Update the docs (the docs rules in [CLAUDE.md](../../CLAUDE.md)), then commit when the user asks.
- Write the pass down as a section "The closing review of slice N" (examples: 17.21 and 17.23).

**2. At the end of a session, Claude gives the user the best prompt to continue in a new
session.** Claude does this when the session is long or when the user asks. The prompt has a
normal length, not a very long one: where we stopped (slice, branch, last commit), what to read
first (pages of `docs/`), the next job, the rules that bite (the user types the
product code, nothing is committed on `main`, the docs rules), what is not done, and the first
command to run. Claude sends it as the last message of the session. A copy of the current
prompt lives in the memory file of the Step 2 plan.
