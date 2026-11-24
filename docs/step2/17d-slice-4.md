# Section 17.19 to 17.21: slice 4, the planner

[Docs home](../README.md)

#### 17.19 Slice 4, lesson 1 (function calling) was done, 2026-10-18

**Status: DONE.** Taught and run on 2026-10-18, on the branch `feat/planner` (made by the user from `main`, `08a355d`). The user typed `examples/function_calling/ask_for_a_plan.py`; Claude checked only its syntax (parsed, not run, to save quota); the user ran it. When this was written the file was not committed yet. The result:

```
STATUS 200   functionCall  make_plan
steps    ["extract_claims", "find_bugs", "verify", "respond"]
queries  ["paper A gradient clipping value 1.0", "code B gradient clipping value 1.5"]
137 tokens in, 58 out, model gemini-3.5-flash-lite
```

**What the lesson taught** (do not re-teach). (1) The direction: the model WRITES the function name and the arguments, our code reads them, and the model never runs anything. (2) `make_plan` is a shape only (case 2 in 19.2): no real function exists, the arguments are the answer. (3) `toolConfig` with mode `ANY` and `allowedFunctionNames` forces the call. (4) The idea behind it, constrained decoding: at each step only the allowed tokens keep their probability and the rest is rescaled. It was NOT checked that Google does it this way, and a tier may only ask for the shape without forcing it, so the code must check the plan anyway.

**Facts measured with three live runs by Claude** (Flash-Lite, exit `185.204.170.210`, AS57568 ARVANCLOUD, Frankfurt, Google 200): mode `ANY` with `allowedFunctionNames` works. Mode `AUTO` with `allowedFunctionNames` answers 400 "Please set allowed_function_names only when function calling mode is ANY". Mode `AUTO` without names also called `make_plan`, but a greeting in `AUTO` was NOT tested (the test script had a mistake: `"hello" and "question"` returns the second text). The same question at temperature 0 gave different step lists in different runs: `summarize, find_bugs, verify, respond` once (`verify` without `extract_claims`), and `extract_claims, find_bugs, verify, respond` twice. The reply also carries an `id` and a `thoughtSignature`, which we ignore. Quota: 4 Flash-Lite requests (3 by Claude, 1 by the user) of 500 a day.

**What the output showed, and what lesson 2 and 3 do about it.** (a) The queries are plain text with the side written inside the words ("paper A ...", "code B ..."). The real plan needs a `side` field on each query (D2 shows `{"side": "B", "text": ...}`), so lesson 2 adds `Query(side, text)`. (b) The planner listed `verify` and `respond`. In the real list `verify` is part of the `extract_claims` step and `respond` is added by code (D31), so the allowed names must come from code, which is lesson 3. (c) Names came from a list but the combination was not sensible in one run, so the plan is checked in code (lesson 3).

**Slice 4 grows from 3 lessons to 5 (an estimate).** Checked on 2026-10-18: `labpilot/llm/` has no tool support at all (no `tools`, `tool_calls` or `functionCall` anywhere), and the first count of 3 forgot it. The plan now: 1 function calling (DONE); 2 the planner node with a fake planner function (`agent/plan.py` holds `Query` and `Plan`, `agent/planner.py` holds the node, `State` gets the key `plan`, and the graph gets an optional `plan` parameter and runs the planner first); 3 the check in code and the default plan; 4 tool calls in the LLM layer (CC4); 5 the real planner function (`api/planning.py`, the fixed instruction, the map, the dynamic budget CC8, and the measurements M5 and M16). **A trap for lesson 5:** `Plan` and `Query` are classes inside `State`, so they must be added to `SAVED_TYPES` in `api/checkpoints.py` when the planner is wired (D37), or a saved chat brings them back as plain dicts. Also written the same day: D48, M15 and M16 (the Jev measurement for `verify` and for the planner's steps, commit `08a355d`).

#### 17.20 Slice 4, lessons 2 to 5 were done, 2026-10-18 and 19

**Status: DONE.** The user typed all the product code, lesson by lesson, on the branch `feat/planner` (five commits, `1c48e83` to `0acf417`), and then the richer map of lesson 5 (the signatures and sentences, below). The planner is BUILT and TESTED. It is **not wired into `ask()`** (`_ask_graph` passes neither `plan` nor `summarize`; slice 5 wires them, together with `respond`).

**What each lesson built:**

| lesson | files | what it is |
|---|---|---|
| 2 the planner node | `agent/plan.py`, `agent/planner.py`, `State.plan`, `build_graph(plan=...)` | `Plan(steps, queries, source)` and `Query(side, text)` are frozen value objects. The node calls the function it is given, `plan(question, a, b)`, and the planner runs before `measure` |
| 3 the check in code | `agent/plan_check.py`, `agent/errors.py` | `STEPS_BY_FILES` (0 files: no step; 1 file: `summarize`, `find_bugs`; 2 files: five steps), `MAX_QUERIES = 12`, `present_sides`, `allowed_steps`, `default_plan`, `problem_with`, `check_plan`, and `PlanError`. A plan the rules reject is replaced by the default plan (every allowed step, the question searched on each side) |
| 4 tool calls in the LLM layer | `llm/contracts.py` (`Tool`, `LLMResult.arguments`), `llm/_calls.py`, `HTTPProvider.complete(tool=)`, Gemini, OpenAI-compatible and Cline readers | "Detect, never configure": the tool is ALWAYS sent. A function call in the answer is used; if there is none, the first JSON object in the text is read; if there is no object either, the tier fails and the chain goes on. The JSON instruction is added to the prompt for tiers that ignore `tools` |
| 5 the real planner | `agent/plan_schema.py`, `prompts/planner.py`, `api/planning.py` | `make_planner(conn, client)` reads the headers of each side, builds the map, asks with the `make_plan` tool, and reads the arguments. The schema holds the allowed steps and only the sides that have a file |

**Decisions.**

- **D50. A plan that is readable and wrong goes to the NEXT tier, not straight to the default plan** (the user's demand, 2026-10-19). `LLMClient.generate(..., problem_with=)` takes a function that returns a reason or `None`. A rejected answer is recorded as an `Attempt`, the tier is not asked again, its quota pool is NOT retired, and the walk stops after `max_rejected_answers` (default 3, `DEFAULT_MAX_REJECTED_ANSWERS`; a first guess that M16 may move). The planner node still runs `check_plan` as the last guard, and a planner that fails never stops the answer.
- **D51. The map budget is computed for each call** (this is CC8). `B_map = max(1, min(PLANNER_BUDGET = 12,000, PLANNER_INPUT_LIMIT = 14,500 - f))`, where `f` is the size of the prompt without the map plus TWICE the size of the schema: the schema goes in `tools` and again as text in the JSON instruction. 14,500 is Gemma's 16,000 tokens a minute divided by the 10% margin of the length check; a test ties it to the tightest `max_input_tokens` in `CHAIN`.
- **D52. The map shows signatures and first sentences** (the user remembered a richer outline, 2026-10-19). `StoredHeader.opening` is the first `OPENING_CHARS = 300` characters of a chunk, and only of a chunk that STARTS its unit (the SQL gives `''` for `part N/M` with N of 2 or more; the pattern keeps the separators, so a folder called `part 2` does not match). `read_headers(..., opening_chars=0)` sends nothing by default. `prompts/_hints.py` has `describe(name, opening)`, which gives `(signature, note)`: a Python `def` or `class` is found BY NAME (decorators kept, a signature over several lines joined, `async` kept) with one line of its docstring; a Markdown section gets its first sentence only when a heading equals the unit's name; display formulas are skipped; a text that was cut is never shown half-written. The ladder is: rich map, the same map with bare names, ranked, folded by folder. On the sample pair the map costs 868 tokens before, **2,150 rich** and 1,284 with bare names (the ceiling is 12,000). `PLANNER_VERSION` is 2. By rule D45 the work was split: `corpus_map.py` went from 454 to 310 lines and `_hints.py` has 148.

**Checked, and what that does NOT show.** Four live planner calls on Flash-Lite (exit `185.204.170.210`, AS57568 ARVANCLOUD, Frankfurt, Google 200) used real names from the files in their queries (`BCEWithLabelSmoothing`, `find_optimal_threshold`, "base learning rate of 3e-4"). That is four calls on one tier and one sample pair: it is NOT a measurement that the plans are better (M5 owes that).

**Owed.**

- M5 (the map with and without, the budget sweep, the summaries arm, the query cap) and M16 (an LLM planner against Jev) were NOT run. Both spend quota and want the new test pair of slice 12. They moved to slice 13 on 2026-10-20.
- The planner does not give `build_map` the file scores yet (`file_scores` exists in `store/`), so a map that does not fit is cut in the file's own order.
- D47 (the stored summaries beside the map) is not built.
- First guesses, not measurements: `MAX_QUERIES = 12`, `STEPS_BY_FILES`, `max_rejected_answers = 3`, `OPENING_CHARS = 300`, the 110-character cap of a row.
- The hints are all-or-nothing: once the rich map does not fit, even the closest files show bare names. Only Python and Markdown units get hints; PDF pages, notebook cells and Word files get none.

#### 17.21 The closing review of slices 3 and 4, 2026-10-19

*The full review pass of slice 3 was forgotten, so one pass covered both slices. The user asked for the system to be seen from above, and the standing question was the usual one: **which real failure is still unprotected?***

**Two real defects, both found by running the suite instead of reading it.**

1. **`total_budget: float = (DEFAULT_TOTAL_BUDGET,)` in `llm/chain.py`.** A trailing comma made the default a tuple, so EVERY `LLMClient()` call failed with `TypeError: unsupported operand type(s) for +: 'float' and 'tuple'` before it sent one request. It came in with the lesson 5 commit `0acf417`, and `test_first_tier_answers_without_touching_the_rest` caught it the moment the suite ran; the suite had not been run after that commit. Fixed (one token). **Run the whole suite before every commit.**
2. **`prompts/__init__.py` imported `OPENING_CHARS` from `corpus_map`** after the split moved it to `_hints`, so the whole `labpilot.prompts` package, and with it the app, failed to import. Fixed.

Both were product code and were fixed by Claude, once, so that the tree could be committed. That was an exception to the rule that the user types all product code, and it was said plainly to the user.

**Tests added** (all written by Claude and checked by deliberate breaks; every break was caught by the test meant to catch it, results below):

| file | tests | what it guards |
|---|---|---|
| `tests/integration/test_planner_over_the_store.py` | 9 | the whole line, with only the provider's wire mocked: real rows, the SQL opening, the map, the request (the tool and the signature are in it, no body text is), the answer, the next tier on a wrong plan, a JSON answer in a code fence, and the plan saved in the real chat memory as a `Plan` |
| `tests/integration/test_summaries_over_the_store.py` | 4 | the parts reach the provider in `chunk_index` order, a big artifact is cut and says so, and the two summaries run at the same time over ONE connection (a barrier makes a graph that ran them in a line fail) |
| `tests/unit/test_architecture.py` (2 tests) | +2 | modularization rules 3 and 2 were only prose: no module past 400 lines unless it is named (the only name is `llm/registry.py`, which is data), and no code imports a file of another package |
| `tests/unit/llm/test_tool_calls.py` (2 tests) | +2 | a new provider class in `CHAIN` that works for text and never reads a tool call is caught: the chain may hold only kinds that have tool tests, and each kind puts the tool in its request |
| `tests/unit/test_docs.py` | 2 | CLAUDE.md and DETAILS.md must not drift (the rule was broken once, on 2026-10-11): every section heading of the first is in the second, with five excused by name |
| `tests/smoke/test_summary_answers.py` | 1 | the summarizer had no weekly live check (needs `--run-smoke`; not run) |

**Not added, and why.** A weekly tool-call test for every tier: M3 measured it once, and "detect, never configure" deliberately keeps no list per tier. A test that the planner and the summarizer are NOT wired: that is a plan, not a behaviour. The check of the 400-line limit does not look at tests, which are allowed to be long.

**Numbers.** `ruff check` and `ruff format --check` are clean. Unit and api: 1241. Full suite without `--run-smoke` (database tests included): 1374 passed, 120 skipped. Deliberate breaks: 42, on the new code and tests: 20 on the map and the planner prompt, 7 on the SQL opening and 15 on the new integration, architecture, tool-kind and docs tests. Every one is caught by the test meant to catch it, after one missing test was added (the ranked form of the map).

**Branches.** The slice 4 work is on `feat/planner` as one commit with this review and on `main` as one file per commit, both pushed (the user's explicit request on 2026-10-19).
