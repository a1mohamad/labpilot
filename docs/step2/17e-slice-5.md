# Section 17.22 and 17.23: slice 5, run the plan

[Docs home](../README.md)

#### 17.22 Slice 5, lesson 1 was done, 2026-10-19

**Status: DONE.** Taught on 2026-10-19. The user typed `examples/langgraph/graph_with_send.py` on `feat/plan-to-run`, ran it with `py -m examples.langgraph.graph_with_send`, and committed it (`00cb059`). The output matched the one Claude got on a scratch copy outside the repo:

```
1 queries    1.0s   chunk for lr
3 queries    1.0s   chunk for lr | chunk for clip | chunk for seed
5 queries    1.0s   chunk for a | chunk for b | chunk for c | chunk for d | chunk for e
```

The user's file has two extra blank lines and wider spaces in the print line; `ruff check` and `ruff format --check` pass on it. A toy in `examples/` has no test. No file in `labpilot/` changed. The user did not report the three breaks of the lesson (A: no add rule, B: zero queries, C: a typo in the node name), so it is unknown if they ran them.

**What the lesson taught** (do not re-teach):

- `Send(node, input)` is one message: "run this node once, with this input". A function on a conditional edge returns a list of them, one for each query, and LangGraph runs them in the same step. It is the fan-out of slice 3, but the number of branches is decided while the program runs: the planner returns 1 to 12 queries, so the nodes cannot be drawn in advance. In plain Python it is `pool.map(search_one, queries)`.
- Three rules, each tested. (1) The node gets only the input of its `Send`, not the state: `task["queries"]` gives `KeyError: 'queries'`. (2) The result key needs the add rule (`Annotated[list, operator.add]`): without it, 3 queries give `InvalidUpdateError`, but exactly 1 query works with no error, so the bug stays hidden until the first plan with 2 or more queries. (3) A node after the fan-out runs once, after all the runs, and the results are in the order of the `Send` list and not in the order the runs finished (the slowest query first stayed first).
- The list `["search_one"]` in `add_conditional_edges(START, fan_out, ["search_one"])` is for drawing the graph and does not stop a wrong name. The conditional edge goes from `START` to `search_one`; `fan_out` is a plain function and not a node (like `pick` in 17.13).
- The math: `T_line = sum of t_i` and `T_Send ≈ max of t_i`, where `t_i` is the time of search number `i`.

**Measured by Claude on a scratch copy** (Python 3.13.14, langgraph 1.2.12; the scripts are not in the repo):

- 12 runs of 0.5 s took 0.5 s, 40 took 1.5 s and 100 took 3.5 s, so the runs use a limited number of threads. The exact rule (how many threads) was NOT checked, so "a slower machine may need two rounds" is a guess. `MAX_QUERIES = 12` fits one round on the development machine.
- Zero queries: the result is `{'queries': [], 'found': []}`. There is no error, `join` never ran and there is no `report`.
- A typo in the node name inside `Send`: one log line (`Ignoring unknown node name search_on in pending sends`), then the run ends with `found` empty and no `report`.
- A list returned by the conditional function may mix a plain node name and `Send` objects (tested: it works).

**Questions of the user, and the answers** (do not repeat):

- Is `Send` a kind of fan-out? Yes; only the "how many" is decided at run time.
- Is the number of queries fixed at 12? No. `MAX_QUERIES = 12` in `agent/plan_check.py` is only a cap. The default plan has 1 or 2 queries (one for each side that has a file), a plan for zero files has none, and a normal planner answer has maybe 3 to 8 (a guess; M5 owes the real number).
- Does `search_one` mean the first artifact? No: it is the node that searches ONE query, and it runs once for each query. The name is Claude's and can be changed (for example `search_query`).

**Proposal for lessons 2 and 3** (the names are confirmed when each lesson starts, D45):

| lesson | piece | file |
|---|---|---|
| 2 | the state key `found` with the add rule | `agent/state.py` |
| 2 | the node that searches ONE query | `agent/search_one.py` (new) |
| 2 | the function that makes one `Send` for each query | `agent/fan_out.py` (new) |
| 2 | the merge node: remove duplicates, apply the budget | `agent/merge.py` (new) |
| 2 | the real search for one query | `api/searching.py` |
| 3 | the final node `respond` | `agent/respond.py` (new) |
| 3 | only the new arrows; `plan` and `summarize` handed in | `agent/graph.py`, `api/asking.py` |

**Open for lesson 2** (design points, NOT decided with the user):

1. **An empty list must be handled on purpose.** The zero-file plan has no queries, and `default_plan` with no sides gives `queries=()`. The toy shows that an empty fan-out ends the run quietly. The real graph was not tried, but it would likely end without `prompt` and `generate`.
2. **Where the rerank runs.** The old rule in the retrieval design ("Six queries, ONE rerank") is: search for every query, merge, remove duplicates, then rerank ONCE against the ORIGINAL question, for each side. Then `search_one` would do the embed, the vector search and the keyword search only, and not the rerank. This is Claude's reading of the old rule and must be decided with the user.
3. **Many searches at once share one database connection** and call the embedders at the same time. psycopg locks the connection for each query, so the reads queue up; this was not tested (the same open point as the two summaries, 17.17). The per-minute limits of the embedders against up to 12 calls at once were not measured.
4. `SAVED_TYPES` in `api/checkpoints.py` already holds `Plan` and `Query` (checked 2026-10-19), so the saved plan needs no new entry. A new class that goes into `State` still needs one (D37).

**Process notes.** The popup question about the branch (the AskUserQuestion tool) was declined by the user, so the branch question was asked in plain text, and then the app quit; Claude continued from git, which had not changed. Claude does NOT commit: the user committed the toy file and asked Claude only to write these notes. Claude wrote them to CLAUDE.md and DETAILS.md in the same session (the two-file rule).

**Update 2026-10-20, before lesson 2 was typed: the design changed twice (D53, D54).** The user asked what
others do when a question makes many queries, and a search showed the usual order is: search with all
the queries, merge, remove duplicates, rerank ONCE, cut to a small number. Lesson 2 as first written
reranked every query on its own (up to 12 reranks). It was rebuilt in the scratch copy, and the user
agreed to both changes:

- **D53, rerank once per side.** `search_one` only searches. The merge node groups the lists by side,
  mixes them by rank, drops duplicates, and calls an injected `rank_side(question, pile)` once for each
  side. The real function is `rank_pile` in `api/searching.py` (window 20, keep 10, or 15 when no tier
  answered). `build_graph` gets a new argument `rank_side`.
- **D54, fewer queries and the question always searched.** `MAX_QUERIES` 12 to 6, the planner is told
  2 to 5 (`PLANNER_VERSION` 3), and `fan_out` puts the question on each side that has a file in front of
  the planner's queries. This closes open points 1 and 2 above (an empty plan, and where the rerank runs).
- **Also fixed:** `build_map` did not count the join between the two sides in its budget.
- **M5 and M16 moved from slice 4 to slice 13** at the user's request: the planner is only measured once
  it runs in the real flow, and that starts with slice 5 lesson 3.

Checked on the scratch copy only (the user's repo was not touched): 1,288 unit and api tests pass, 24
deliberate breaks were caught (17 for lesson 2, 7 for D54), and the 9 planner database tests pass. Two
`test_ask` database tests stopped on a statement timeout and a dropped connection over the VPN and were
not run again. The user types the code. The tests come after the user says "typed". Three old tests must
change: `test_plan_check` (12 queries to 6), `test_planner` (the old wording) and the map test in
`test_corpus_map` gets one new case. Lesson 3 must pass `rank_side=rank_pile`, remove the old `search`
path (`retrieved_chunks` and its only reason to exist, `rerank_and_cut`), and decide what to do with
`rerank_and_cut` and its tests.

#### 17.23 Slice 5 is DONE: lessons 2 and 3, the pool, the move to `search_one` only, and the closing review — 2026-10-20 and 21

**Status: DONE.** Slice 5 is closed. The user typed lessons 2 and 3 on `feat/plan-to-run`
(commits `3a46eb3` to `839ca21`). On 2026-10-21 Claude removed the old search, ran the review
pass of the new rule (Working Rules) and wrote these notes, at the user's request, as commits on
the same branch: `b47987f` (the move to `search_one` only), `511b63f` (the saver fix, below), `9a3986d` (the review tests) and the docs commit after them. Nothing is on `main` and nothing was pushed.

**Lesson 2 (2026-10-20): one search for each query, all at the same time.**

- `agent/search_one.py` is the node that searches ONE query and writes the chunks into the state
  key `found` (a list that grows, with the add rule).
- `agent/fan_out.py`: `fan_out(state)` makes one `Send` for each query. The user's question is
  searched on every side that has a file, first, and then the planner's queries come (D54). With
  no side that has a file it raises `ValueError` ("nothing to search"); that cannot happen today
  because `ask()` needs both ids (see the open items).
- `agent/merge.py`: `merge_chunks` mixes the lists by rank (the best chunk of each query first)
  and drops duplicates (the key is the artifact id and the chunk index). The merge node makes one
  pile for each side, calls the injected `rank_side(question, pile)` ONCE for each side with the
  user's original question (D53), asks `totals_of(sides)` how many parts each side has, and empties
  `found` with `Overwrite([])`, so the next message does not inherit the chunks of this one.
- `api/searching.py`: `retrieve_query(conn, sides, side=, text=)` is embed, vector search and
  keyword fusion, and it never reranks. `rank_pile(question, pile)` reads the first
  `RERANK_WINDOW` (20) chunks of the pile, asks the chain for the whole order, keeps `RERANK_TOP_N`
  (10), and keeps `VECTOR_TOP_N` (15) from the whole pile when no tier answered. There is no skip
  gate: the best scores of different queries cannot be compared.
- D55, the pool of database connections: eight searches that run together need eight connections.
  `store.make_pool()` builds a CLOSED pool of `POOL_SIZE` = 8, and the first search opens it. The
  lifespan builds it and closes it. `ask(..., pool=)` hands it to `_ask_graph`, and `search_one`
  takes one connection from it for each query. Measured with 8 searches of 7 quick round trips each:
  one shared connection 12.9 s, a pool of 2 6.2 s, of 4 4.1 s, of 8 1.7 s. Not measured: the real
  queries, the memory, and the connection limit of the Supabase session pooler.

**Lesson 3 (2026-10-20 and 21): `respond`, and the summaries join the answer.**

- `agent/respond.py` is the one final node (D31). It replaces the old `prompt` and `generate`
  nodes: it reads `chunks`, `question`, `totals` and the two summaries, builds the prompt with the
  injected `make_prompt`, and calls `generate`.
- The summaries are written on every message, at the same time as the planner: `plan`,
  `summarize_a` and `summarize_b` all start from `START`, and `measure` waits for all three, so
  `respond` can read the summaries on the stuff path and on the search path. A summary that fails
  on every tier becomes an empty text, and the report is written without the block, because a
  summary is a guide and not the evidence.
- `prompts/builder.py` gained `SUMMARIES_NOTE` and a summaries block that sits before the parts.
  The report instruction asks in its section 12 (CORRECTIONS) for corrected code or a better
  algorithm, in the order of section 8, with a stated confidence (D49). The size guard for the
  instructions is 2,200 bytes (`COLLAPSE_BYTES`).
- **A real defect found:** `store.make_pool` passed `connection_timeout` to libpq, whose name is
  `connect_timeout`. Fixed.
- `.github/workflows/smoke.yaml` now starts a `pgvector/pgvector:pg17` service container, sets
  `DATABASE_URL` (no secret) and installs the extension, because the smoke test for the ask path
  needs a database. `test_the_smoke_run_really_has_a_database` fails the build if that is lost.

**The move to `search_one` only (2026-10-21, D57).**

- The old one-shot `search` node is gone. `build_graph(*, measure, fits, stuff, search_one,
  totals_of, rank_side, plan, make_prompt, generate, summarize=None, checkpointer=None)` REQUIRES
  `search_one`, `totals_of`, `rank_side` and `plan`. There is no default, so no graph can be built
  the old way and no half-wired graph exists. After `measure`, a conditional edge sends the run to
  `stuff` when the pair fits and to the fan-out when it does not.
- Deleted from `api/searching.py`: `retrieved_chunks` and `rerank_and_cut`. Older notes in these
  files that name them mean `retrieve_query` and `rank_pile` now.
- **The skip gate is now unused.** `retrieval/gate.py` (`should_rerank`, `margin`, `SKIP_MARGIN`)
  has no caller in `labpilot/`; its own tests stay. Slice 13 decides: delete it, or give it a
  caller. The test that forced the gate to say NO was deleted with the function it tested.
- `scripts/timing/bench_end_to_end.py` times `asking.rank_pile` now.

**The closing review of slice 5 (2026-10-21).** Looked at from above, the new slice joined four
things that no test crossed together. Four tests were added, and the old ones were moved.

| new test | the join it protects |
|---|---|
| `tests/integration/test_ask.py::test_many_queries_make_one_pile_per_side_with_no_duplicates` | real rows, three plan queries, five searches: no chunk comes twice and each side keeps exactly `VECTOR_TOP_N` |
| `...::test_a_report_is_still_written_when_the_planner_fails_on_every_tier` | the planner failing on every tier still gives a report, from the default plan (the question on each side) |
| `...::test_a_chat_on_the_searched_path_is_saved_and_comes_back_as_real_objects` | the real Postgres saver with `Send`, `Overwrite`, `Plan`, `Chunk` and `StoredArtifact` in the state; the stuffed path never met them |
| `tests/unit/test_scripts.py` (34 tests) | every name a script takes from `labpilot` still exists, and the functions the benchmark times still exist. This would have caught the stale script of this very migration |
| `tests/unit/agent/test_graph.py` (rewritten) | the full order of calls on both paths, and the four functions are required, with `search` gone (by signature) |
| `tests/api/test_checkpoints.py` (+3) | the saver does not use pipeline mode, and its `executemany` sends one statement at a time (the defect below) |

Moved: the tests of `rerank_and_cut` were deleted, because the six tests of `rank_pile` in
`tests/api/test_rank_pile.py` hold the same rules (the two number spaces, the whole order asked
for, the cut after the call, the degraded cut, the empty pile). `test_ask.py` (api) keeps only the
query-embed tests, and `tests/api/test_retrieve_query.py` and `tests/api/test_fusion_is_on.py` call
`retrieve_query`.

**A real defect found by the review pass: the chat save failed on a real size.** The first full
run had one red test, the new chat test on the searched path, with `SSL error: bad length`. It was
not a flake. The saver (LangGraph's `PostgresSaver`) writes the checkpoint with psycopg's
`executemany`, and psycopg runs `executemany` in PIPELINE MODE. libpq has a bug there
([PostgreSQL bug report #18907](https://www.postgresql.org/message-id/18907-d41b9bcf6f29edda%40postgresql.org)):
when a large message goes over SSL and the network takes it in several pieces, the next message is
added to the output while the first write is still being retried, and OpenSSL stops with `SSL
error: bad length` (also seen as `connection not in pipeline mode`). A chat on the search path
saves about 150 KB (the prompt, the text of the chunks, the report). The stuffed path saves a few
hundred bytes and never failed. How it was found: the connection was traced thread by thread
(no other thread used it at that moment), three variants were compared (shared connection, a
pool, searches one at a time: all failed at the same rate, 9 of 15), and a plain stress test of
three threads on one connection gave no error in 360 queries. Only a large save in pipeline mode
fails. **The fix, `api/checkpoints.py`:** `open_saver` returns `_SafeSaver`, a `PostgresSaver` with
`supports_pipeline = False` (one transaction, same statements) whose cursor is wrapped by
`_OneAtATime`, so that `executemany` runs one `execute` for each row. The price is a few more round
trips of about 0.12 s on a report that takes minutes. **The honest limit:** the failure depends on
the network (about half the runs of one afternoon, none of the next hour), so no integration
test can hold the rule. A test that saves 400 KB eight times was written, passed with the OLD saver
too, and was deleted (a test that cannot fail). The rule is held by two deterministic unit tests
(the flag, and the one-at-a-time `executemany`). Repeated eight times after the fix, the searched
path chat test passed eight times.

**Deliberate breaks, all caught by the test meant to catch them:** the benchmark naming a removed
function; a script importing a removed name; `plan` made optional again; the question no longer
searched on each side (16 tests); `pick` ignoring `fits` (4 tests); the merge keeping duplicates;
the planner node not catching `PlanError`; `found` no longer emptied; the plain saver back (the
flag test); the pipeline flag back on (the flag test); the `executemany` wrapper doing nothing (two
tests). Each break was made on the file itself with the original bytes kept aside, and the file was
restored from those bytes.

**Suite on 2026-10-21: 1503 passed, 120 skipped** (unit, api and integration, without `--run-smoke`), `ruff
check` and `ruff format --check` clean.

**Open items (none is fixed).**

- `fan_out` raises `ValueError` when no side has a file. Today `ask()` and the API need both ids,
  so it cannot happen. **Slice 6 must handle 0 and 1 file** (D56).
- The saved chat still holds the whole prompt (up to about 78,000 characters) and the text of
  every chunk. After each message only the newest copy stays, so the growth is per chat, but the
  size of a chat with a real search path was NOT measured.
- The window of 20 was measured on the pile of ONE query; with many queries it holds about the
  top 2 of each. A larger window or a rank by how many queries found a chunk are the options (D53).
  Slice 13.
- M5, M16 and M17 (slice 13); D46 and D47 (slice 12 and later).
- The skip gate has no caller (above).
- **`store/writer.py` also uses `executemany`** (the ingest of an upload, in batches of 96 chunks
  with their vectors, over a megabyte each), so it runs in pipeline mode too and could meet the
  same libpq bug. It did not fail in the tests (small batches over the VPN), and the ingest of
  81,000 chunks in slice 4 went into a LOCAL container, so it says nothing about SSL. NOT
  measured: a real repository uploaded to Supabase through the app. Do that once (the repository
  door, about 500 chunks). If an upload ever fails with `SSL error: bad length`, give the writer
  the same one-at-a-time cursor.
- Both the saver and the writer should be looked at again when psycopg-binary or libpq changes.
