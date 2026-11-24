# Traps that still bite

[Docs home](../README.md)

### Traps that still bite — each was found the hard way

- **The two number spaces.** `search()` returns `SearchHit.chunk_index`, an ID in the corpus. `rerank()`
  returns POSITIONS into the list it was handed. `hits[p]` is right; looking up chunk `p` cites the wrong
  file and line with full confidence. Two test files number their ids from 100 so the confusion is
  provable rather than plausible.
- **`skip()` truncates to whatever `top_n` it is handed**, so the cut must happen AFTER the call and
  `rank()` must be asked for everything. Both halves are pinned by tests.
- **A fixture numbered from zero, or holding one chunk, cannot fail.** A one-chunk file cannot tell a
  correct `start_line` from a lost one, and ids starting at 0 cannot tell an id from a position. Both
  were found by mutation, not by reading.
- **Spending quota makes a suite slower, never redder.** `_best` took its chain as a DEFAULT ARGUMENT
  evaluated at import time, so monkeypatching the module attribute never reached it and every test run
  spent live rerank quota (four Gemini tiers, then Cohere's 1,000-a-MONTH). `tests/conftest.py` now
  keeps the rerank chain empty outside smoke.
- **`database` tests are green-by-absence.** They skip themselves when `DATABASE_URL` is missing, so
  read the skip reasons (`pytest -q -rs`) before believing a count. CI runs a `pgvector/pgvector:pg17`
  service container (no secret; 533 tests in ~15 s against ~40 s over the VPN to Supabase), and
  `test_ci_really_runs_the_database_tests` fails the build if the workflow ever loses `DATABASE_URL` or
  the service.
- **The page.** Trust a DOM read over a screenshot (the browser pane's screenshots once went stale
  mid-session while `result.hidden` was false and `/compare` had returned 200). A CSS `display` rule beats
  the `[hidden]` attribute, so `[hidden]` is forced off globally. Two cards sat out of line because one
  hint wraps and the other does not — found by LOOKING, not reading.
- **A rewound session can revert files on disk while git still holds the right versions.** Check
  `git status` and `git diff` before rewriting anything; `git checkout -- <file>` restores to whatever HEAD
  is NOW (see the mutation-testing rule in Conventions).
- **A one-token typo can break every call, and only the suite shows it.** `total_budget: float = (DEFAULT_TOTAL_BUDGET,)` (a trailing comma made a tuple) came in with the lesson 5 commit and every `LLMClient()` call failed before its first request. Run the whole suite before each commit, not after (17.21).
- **A save of a real size fails in a way a small test never shows.** psycopg's `executemany` runs in pipeline mode, and libpq has a bug there (PostgreSQL bug report #18907): a large message over SSL fails with `SSL error: bad length` when the network takes it in pieces. The chat save of the search path (about 150 KB) failed in about half the runs of one afternoon and in none the next hour. `open_saver` sends one statement at a time now; `store/writer.py` still uses `executemany` and has not been tried with a big upload through SSL (17.23).
- **Never size a benchmark to the machine you wish you had.** A 30,000-row HNSW build with
  `maintenance_work_mem=512MB` took the Supabase free instance down on 2026-09-05. Run that class of
  work on a local container.
- **Check the exit ISP before any call that spends a model** — the rule and the two commands are in
  [the network precondition](sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work).

- **2026-10-24 (night)** — slice 7: all measurements ran (M10, M11, M21, M24, M15, the D74 baseline) and the closing review was done, with nothing written into the repository while a `merge_per_file.py` run needed a clean tree. The big result is that A must be read in groups of about 2,000 tokens (R1); the baseline on the search path is weak and the user asked whether the system finds the real causes (25.9). The review found a real defect (one failed claim search loses the whole answer), two stray `+` characters in the claims instruction, and no weekly live test for the three new calls; 11 tests and three patches were handed over in `artifacts/slice7-review/` → section 25. **Next: type the patches, decide R1 to R24 (the complete list is in 25.11), design the cause-finding step (R13), and also try the stuffed approach (the user's plan for the next session).**
- **2026-10-24 (late night)** — slice 7: every change of 25.11 built and measured by Claude at the user's request (R1-R24 but R11 and R12), with Step 1 re-checked: R23 (fill the budget) is the big win, the rerank window and rerank itself change nothing on this pair, the stuffed path keeps all of B (parts first) and answers at once (R21), the citation ids are one list again, the never-called reader is fixed, CHECK v3 → section 26.
- **2026-10-29** — slice 8 started on `feat/correspondence-gate`. The cosine gate of 2026-08-11 was replaced by the user's idea: compare the two summaries with ONE function-calling call (verdict FULL, PARTIAL or NONE plus a reason), the planner runs beside it, and on NONE a prepared answer from the two summaries ends the run. Decisions D78 to D83, measurement M28 and the files are in [section 28](../step2/28-slice-8-gate.md#28-slice-8--the-correspondence-gate-redesigned-on-summaries--decided-2026-10-29). Summaries at ingest (slice 12) and Jev as the gate (slice 14) were kept as later moves. Nothing is built yet.
