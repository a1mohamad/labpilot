# Section 17.16 to 17.18: slice 3, parallel nodes

[Docs home](../README.md)

#### 17.16 Slice 3, lesson 1 was done, 2026-10-17

**Status: DONE.** Taught on 2026-10-15, run by the user on 2026-10-17. The user typed
`examples/langgraph/graph_with_parallel.py` and ran it from the repository root with
`py -m examples.langgraph.graph_with_parallel`. The output:

```
parallel=False    2.0s   A is about paper | B is about code
parallel=True     1.0s   A is about paper | B is about code
```

The file holds one `State` (`a`, `b`, `summary_a`, `summary_b`, `report`), three nodes (`summarize_a` and
`summarize_b`, each with `time.sleep(1)`, and `join`) and two graphs. In a line: `START -> summarize_a ->
summarize_b -> join`, so the time is 1 + 1 = 2 seconds. In parallel: `START` goes to both summary nodes, and
`add_edge(["summarize_a", "summarize_b"], "join")` makes `join` wait for both, so the time is the longest
branch, 1 second. The file and the D45 rule are committed together in `18b2948` on `feat/parallel-nodes`. No
product code was changed in lesson 1.

**What the user now knows** (settled in a long question and answer; do not re-teach). The uneven-branch case was
tested with scratch scripts, which are not in the repo.

- **Fan-out** means more than one arrow leaves a node (or `START`), so several nodes run in the same step.
  **Fan-in** means a node waits for them. In LangGraph they come together: there is one `START` and one `END`,
  and `END` is an automatic join that runs no code. Only the explicit join node is optional (it is just the
  place where the results get used).
- Arrows carry order, not data. Data travels in the state.
- A conditional edge is a choice (if / else), not a fan-out. A node that two branches of a choice both point to
  (like `prompt` in the real graph) is a meeting point, not a fan-in: only one parent runs.
- `add_edge(["a", "b"], "join")` waits for ALL parents. Two separate arrows into one node start it when ANY
  parent finishes. If the branches have different lengths, the node runs twice, the first time on old data
  (in the scratch test the first run saw `'A first draft'`), and everything after it runs twice.
- Two nodes that write the same key in the same step: without a reducer, `InvalidUpdateError`. In a line, the
  later write replaces the earlier one. With `Annotated[list, operator.add]` both are kept, in node order and
  not in finish order. Different keys (`summary_a` and `summary_b`) need no reducer.
- A plain `def` node runs in a Python thread (one sequence of work), as a FastAPI `def` route does. The GIL is
  released while a thread waits for the network, so two model calls overlap. `thread_id` (the chat name) has
  nothing to do with Python threads. Async is different: one event loop that switches only at an `await`, so the
  second task starts while the first one waits, and a blocking call inside `async def` freezes everything.
- `invoke` returns after the slowest branch. One graph has one `END`; the caller reads the state, and
  `StateGraph(State, output_schema=Out)` limits the keys that come back.

**Mistakes of Claude in this lesson, so they are not repeated.** (1) Claude called `prompt` a "fan-in without
fan-out"; it is only a meeting point after a choice. (2) Claude said fan-out can live alone; the user was right
that `END` is the automatic fan-in (checked with `draw`). (3) The first uneven-branch test did not show real
damage; a better one with `improve_a` did. (4) A thread was described as "one line of Python work"; it is one
sequence of work. (5) The async order was first described wrongly: the loop starts B at once while A waits.

**Lesson 2, the file plan (D45), asked on 2026-10-17 and confirmed when the user typed it (17.17). The `api/summaries.py` row moved to lesson 3:**

| file | what goes in it |
|---|---|
| `labpilot/agent/state.py` (new) | The `State` class moves here, with two new keys, `summary_a` and `summary_b`. |
| `labpilot/agent/summarize.py` (new) | The node as a factory: it receives a model function from `api/` (D7) and returns the node. |
| `labpilot/agent/graph.py` | Only the new arrows: one summary node per side started together, then a join. |
| `labpilot/api/summaries.py` (new, lesson 3) | The real function handed to the graph, so `services.py` does not grow again. |
| `tests/unit/agent/test_summarize.py` | The tests (copy and paste). |

Open for lesson 2: where the two summaries sit in the existing graph; and the model function is called from two
threads at once. `dead_pools` in `llm/chain.py` is a local variable of each `generate` call, so there is no data
race, but two parallel calls do not share what they learn about dead pools. LiteRouter allows one request at a
time and paces 7 seconds, so two parallel calls on that route can be slowed or refused.

#### 17.17 Slice 3, lessons 2 and 3 were taught, 2026-10-17

**Status: DONE 2026-10-17.** Claude read the files the user typed, fixed five mistakes (listed below), ran the tests, and ran 13 deliberate breaks on a scratch copy: all 13 were caught, each by the test meant to catch it. Unit and api tests: 1053 passed, 5 skipped. `ruff check` and `ruff format --check` are clean. Slice 3 became three lessons (it was planned as two).

**Lesson 2, the summary nodes in the real graph.** Claude first built and checked the same code in a scratch copy of the repo outside it (18 agent tests passed there, 4 deliberate breaks were caught, the repo was untouched). The user typed it in two phases.

| file | change |
|---|---|
| `labpilot/agent/state.py` (new) | `State` moved here (phase A, no behaviour change), then got `summary_a` and `summary_b` (phase B) |
| `labpilot/agent/summarize.py` (new) | `make_summarize_node(source, summarize)`: a factory, a closure that remembers `"a"` or `"b"` |
| `labpilot/agent/graph.py` | imports `State` from `state.py`; new optional parameter `summarize=None`; when it is given, two nodes start from `START` and go to `END` |
| `labpilot/agent/__init__.py` | exports `build_graph` from `graph` and `State` from `state` |
| `tests/unit/agent/test_summarize.py` (new) | 5 tests, copy and paste |

- **No join node.** Nothing reads the summaries yet, and `END` is the automatic join (17.16). Slice 5 adds a real join when `respond` reads them.
- **`summarize` is optional and `_ask_graph` does not pass it.** With `None` the graph is the one from slice 2, and the live app spends no model call on a result nobody reads.
- **A step waits for its slowest node.** All nodes of a step run together and the next step starts when the last one ends. Measured in a toy graph: with summaries that sleep 1 s, `stuff` started at 1.0 s. So a step takes the maximum of its node times, and the whole run takes the sum of its steps.
- **The parallel test needs no sleep.** The fake `summarize` waits on `threading.Barrier(2, timeout=2)`. Two threads together pass it. In a line the first call waits alone and fails with `BrokenBarrierError`. Only this test fires when the nodes are put in a line.
- **The user's first run failed with 16 collection errors and ONE message:** `ImportError: cannot import name 'State' from partially initialized module`. `summarize.py` wrote `from labpilot.agent import State`. Python runs `__init__.py` from top to bottom: line 1 imports `graph`, `graph` imports `summarize`, and `summarize` asks the package for `State`, which line 2 would import. A circle. Fix: `from labpilot.agent.state import State`. **Rule: code OUTSIDE a package imports from its front door; files INSIDE a package import each other directly.** Claude then said the same would break in `prompts/`. That was too strong: there it works only because the `instructions` line comes before the `summary` line in `__init__.py`, so it would be luck. The direct import is the safe habit.

**Lesson 3, the real summary function.** Claude first wrote it WITHOUT running it, because the user said "dont check, i will return the test results myself". Later the user asked Claude to check the typed code and correct it, and then everything was run (see below).

| file | what |
|---|---|
| `labpilot/prompts/summary.py` (new) | `SUMMARY` (a short fixed instruction), `SUMMARY_BUDGET = 12_000`, `SUMMARY_MAX_TOKENS = 4_000`, `build_summary_prompt(parts)` |
| `labpilot/prompts/__init__.py` | exports the four names |
| `labpilot/api/summaries.py` (new) | `make_summarizer(conn, client)` returns `summarize(artifact_id) -> str` |
| `tests/unit/prompts/test_summary.py` (new) | 5 tests |
| `tests/api/test_summaries.py` (new) | 4 tests, a fake client and a patched `read_chunks` |

- **What it reads.** The FIRST parts that fit `SUMMARY_BUDGET`, in order. The cut stops at the first part that does not fit, so "the first K of N parts" stays true. The prompt always says how many parts were sent, so nothing is cut silently. 12,000 is Gemma's 16,000 input tokens a minute divided by the 10% margin of the length check, minus room for the instruction (the same reasoning as `PLANNER_BUDGET`).
- **What it asks.** At most 150 words, plain prose, no citations. Time follows the tokens written, so a short answer takes seconds where a report takes minutes. `max_tokens` is 4,000 only as a backstop: tiers that think spend tokens first, and a small cap would return nothing and waste a tier.
- **Errors.** `AllFreeTiersExhausted` becomes `GenerationUnavailable`, and `UnknownArtifact` becomes `UnknownArtifactId`, the same conversions `generate` and `_sides` do.
- **Not wired.** Slice 5 wires it into `_ask_graph`, when `respond` reads the summaries. Slice 11 gives it a cheap chain: today it would use the full chain, which has 20-a-day models in it. This is scaffolding with a scheduled consumer, like `ask()` before its route.
- **Two threads at once.** `LLMClient.generate` keeps its state in local variables, so two calls share nothing (each learns alone that a quota pool is dead). The database connection is shared; psycopg locks it for each query, so the reads queue up and take milliseconds. This was NOT tested. LiteRouter's 7-second spacing is already reserved under a lock (20.3).
- **Known limits.** Only the first 12,000 tokens are read: about 35 parts, roughly 8 files in a repository like ours (4.4 parts per file, measured). `read_chunks` reads every row before the cut. A summary cut by `max_tokens` is returned as it is.

**The user's decision on big artifacts (D46, in 21.2).** For a repository of 200 files the summary is only the first files in sorted order. The user decided that this plan is too weak: a big repository needs a GOOD summary, and slice 12 owns it.

**The five mistakes Claude found and fixed in the typed files** (the user asked for it): (1) `graph.py` registered the node as `"summarize"` instead of `name`, so both sides used one node name and the arrows pointed at nodes that did not exist; (2) `prompts/summary.py` compared the running total with `SUMMARY_MAX_TOKENS` (4,000) instead of `SUMMARY_BUDGET` (12,000); (3) `api/summaries.py` returned the whole `LLMResult` and not its `.text`; (4) two files had misspelled names (`api/summarize.py` and `test_summarries.py`); (5) `tests/unit/prompts/test_summary.py` was empty. The tests were right: each of the first three mistakes makes at least one test fail. The typo in an error message ("need") was fixed too.

**Mutation check, 13 breaks on a scratch copy, 13 caught, each by its own test.** Examples: running the two summaries in a line is caught ONLY by the barrier test; both nodes writing `summary_a` is caught by 3 tests; adding the summary nodes when `summarize` is `None` is caught by 13 old graph tests; wrong budget, wrong order, a lying "All parts are sent" line, an empty parts list, a missing `.text`, a missing error conversion and a wrong `max_tokens` are each caught by one test. `tests/unit/test_error_boundaries.py` accepts the new `api/summaries.py`, and `tests/unit/prompts/` existed.

**Open.** (1) Commits, one file per commit, on `feat/parallel-nodes`. Lesson 2: `agent/state.py`, `agent/summarize.py`, `agent/graph.py`, `agent/__init__.py`, `tests/unit/agent/test_summarize.py`. Lesson 3: `prompts/summary.py`, `prompts/__init__.py`, `tests/unit/prompts/test_summary.py`, `api/summaries.py`, `tests/api/test_summaries.py`. Then the two docs together. (2) The D45 task (a full read-only check of the whole app, then the split of `api/services.py`) was DONE on 2026-10-18 (17.18). Then slice 4.

#### 17.18 Slice 3 closed: the check of the whole app and the split, 2026-10-18

**Status: DONE.** This was the D45 task that slice 3 owed (Working Rules, "Modularization"). The user asked for the files to be copied in whole and for the work to go on a new branch, `refactor/split-services`, then on `main` one file per commit. Because it is a pure move, this one task is an exception to the rule that the user types all product code; the user allowed it in words.

**What was read.** All 107 `.py` files and `schema.sql` of `labpilot/`, file by file. One exception: `llm/registry.py` (1,273 lines, only data) was read by its top-level names, not line by line, because it changes in slice 11. Two read-only scripts checked the imports and the names. NOT done: the tests were not read, no mutation testing was run, and the smoke tests were not run (they spend quota).

**What the check found.**

- **Layers are correct.** No import goes in a wrong direction. `agent` imports only `ingest`; `store` and `sources` import nothing of ours.
- **Four imports skipped a front door**, all in `api/`: `reranking.py` (`llm.registry`), `services.py` (`agent.graph`), `startup.py` (`llm.chain`) and `uploads.py` (`sources.defaults`). Fixed. Two names needed an export first: `GOOGLE_KEYS` from `labpilot.llm` and `SECRET_SUFFIXES` from `labpilot.sources`.
- **Two files did more than one job.** `api/services.py` (873 lines, four jobs: save a file, read a repository into chunks, search and rerank, run the graph) and `ingest/chunker.py` (three jobs: the lists of loaders and splitters, the refusal of minified files, and the size cap with the merge of small pieces). Both were split.
- **A module name was hidden by a function.** `store/__init__.py` exported the function `search`, and there was also a file `store/search.py`, so `labpilot.store.search` was the function. It is the same trap as `walk` in `sources/`. The file is now `store/vector_search.py`.
- **Two typos:** `OUTPUT_SEPARTOR` in `ingest/_notebook.py`, and "most" for "must" in the error text of `retrieval/selector.py`.
- **One word with two meanings:** `Source` in `agent/summarize.py` was `Literal["a", "b"]`, while `sources.Source` is a folder we read and `chunk.source` is a file name. It is now `Slot`.
- **Every other file has one job.**

**What changed (47 commits, one file each).**

| Before | After |
|---|---|
| `api/services.py` | deleted |
| `ingest_artifact`, `ingest_source`, `_store`, `_pick_embedder`, `_records`, `_cut_bytes`, `_artifact_id`, `_source_id`, `WARN_MINUTES`, `EMBEDDING_MINUTES_BUDGET`, `INGEST_OVERHEAD_SECONDS` | `api/ingestion.py`, same names |
| `chunk_source`, `_newest_owner` | `api/source_chunks.py`, same names |
| `_sides`, `_fits`, `_stuffed`, `_as_chunk` | `api/reading.py`: `measure_sides`, `fits_whole`, `stuffed_chunks`, `as_chunk` |
| `_retrieved`, `_fused`, `_best`, `_embed_question`, `VECTOR_TOP_N`, `RERANK_WINDOW` | `api/searching.py`: `retrieved_chunks`, `_fused`, `rerank_and_cut`, `_embed_question`, same constants |
| `_prompt` | `api/prompting.py`: `build_report_prompt` |
| `ask`, `_ask_graph`, `_forget_old_copies` | `api/asking.py`, same names |
| `store/search.py` | `store/vector_search.py` |
| `_reserve`, `_enforce_cap`, `_merge_small` and their helpers in `ingest/chunker.py` | `ingest/_sizing.py`: `reserve`, `enforce_cap`, `merge_small` |
| `Source` in `agent/summarize.py` | `Slot` |

The code was only moved. The logic did not change: the same tests pass before and after. The routers call `ingestion` and `asking`. Twenty tests and four scripts changed only their imports and patch paths. Every older note in this file that says `api/services.py`, `services._best` and so on means the new place in this table.

**A trap the split made visible.** A test must patch a name in the module that LOOKS IT UP. `monkeypatch.setattr("labpilot.api.asking.prune", ...)` works, because `asking.py` calls `prune`. A thin `services.py` that only re-exports names would have been worse than none: a patch on it could succeed and still change nothing, and the test would call the real function. With `services.py` deleted, an old path fails at once with `AttributeError`.

**How it was tested.** The finished files were built first in a scratch copy of commit `1e5a828`, and the 47 commits were replayed one by one on a clean copy before they were made in the repo. Result in the repo, on the last commit: `ruff check` and `ruff format --check` clean, 1057 unit and api tests passed (5 skipped), 115 database tests passed on a temp schema of Supabase, and 1290 tests collected before and after, so none was lost. The committed tree is identical to the tested copy. The unit and api tests were run before every commit. Every commit is green except three, which are red on purpose because a test and its router must change together: the commits of `tests/api/test_compare.py` and `tests/api/test_errors.py` (13 tests red) until `routers/compare.py` switches, and of `tests/api/test_artifacts.py` (10 tests red) until `routers/artifacts.py` switches. At the `artifacts.py` commit the two chain tests (`test_api_over_the_chain.py`, `test_the_two_doors_together.py`, which need a database) are also red (9 tests, measured on a clean copy) until their own commits. The commit messages of those files say so. The smoke tests were collected but not run, because they spend quota.

**Found and NOT fixed (open).**

- `embed/rates.py`, lines 64 to 69: the line that logs the Cloudflare cost (`cf-ai-neurons`) is inside the `for` loop, so it logs only when a rate-limit header is also present. Checked by running it. No test covers it.
- `Artifact` in `api/contracts.py` is an uploaded file, but `ArtifactRecord` and `StoredArtifact` are database rows. Rename `Artifact` to `Upload` later.
- The same idea is spelled `a`/`b` (state keys), `A`/`B` (`Side`) and `a_id`/`b_id` (in `ask`).
- The conversion "all tiers failed becomes 503" is written in `asking.py` and in `summaries.py`. The planner of slice 4 would be the third copy: write one shared helper first.
- `build_graph` has 8 arguments and each slice adds more. Decide in slice 4 whether to hand the functions over as one small dataclass.
- No test forbids a deep import (rule 2 of the Modularization rule). `test_architecture` checks layers only, and `test_public_api` checks that the names in `__all__` exist.
- Smaller: `SIDES = ("A", "B")` is written 3 times; `REQUEST_ID_HEADER` twice; `INPUT_BUDGET` in `retrieval/selector.py` is an old default that nothing uses; the constant `CLOUDFLARE_RERANK` is in no chain although its comment says "deleted"; `normalised` and `normalized` are both used.
- Later, not now: `llm/registry.py` split by gateway (slice 11); `embed/base.py` could give `embedding_minutes` its own file; `prompts/instructions.py` holds FULL and CORE, which only tests and scripts use; `routers/compare.py` builds the reply, and slices 5 to 7 add to it.
