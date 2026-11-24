# Full text: STEP 2 — the plan, recorded 2026-09-22

[Docs home](../../README.md)

### 4. THE SLICES — fourteen since 2026-10-14 (nine before)

*(Eight until 2026-10-07, nine until 2026-10-14. On 2026-10-14 the user saw that the nine
slices did not build most of the nodes the capability library promises (`summarize`,
`find_missing`, `find_bugs`, the final `respond` node and others), and the list was rewritten
together. The reasons, the new decisions D39 to D44 and the map from every planned node to its
slice are in [section 21](../../step2/21-final-design.md#21-the-final-design-and-the-new-slice-list--agreed-2026-10-14).
Notes elsewhere in this file that name a Step 2 slice were changed to the new numbers. Notes
about Step 1 slices (for example "slice 7 wired the ask path") are history and keep theirs.)*

| # | slice | what it builds | teaching |
|---|---|---|---|
| **0** | **does LangGraph fit?** | the real install tree and resident size against the 512MB ceiling | none — DONE |
| 1 | **latency ranking** | how fast each of the 40 tiers is, and which support function calling | none — measurement, DONE |
| 2 | **the skeleton** | a graph replaces `ask()`, and the chat is saved (checkpointer, `thread_id`) | **heavy** — DONE |
| 3 | **`summarize` + parallel nodes** | the `summarize` node; A and B summarized at the same time (fan-out, fan-in, reducers). The slice ENDS with the modularization task (D45): a full read-only check of the whole app, then the split of `api/services.py` | medium, 3 lessons |
| 4 | **the planner** | the outline is used; ONE call returns the steps and the queries as a shape; the plan is checked in code; a default plan when it fails; the zero-file plan `[respond]` | medium, 5 lessons, **DONE 2026-10-19** (revised 2026-10-18, see 17.19 and 17.20): the small one on function calling (D34, DONE), the planner node, the check in code, tool calls in the LLM layer, the real planner function |
| 5 | **run the plan** | one search per query, all at the same time (dynamic fan-out); the merge step with duplicates removed (D42); the final `respond` node replaces `generate` (D31) and carries the fix part (D49); "stuff when it fits" stays | **heavy**, 3 lessons; lesson 1 DONE 2026-10-19 (17.22) |
| 6 | **follow-ups and `respond` for every case** | the node that rewrites a follow-up question into a standalone one; the first node that reads `history` (D5, D6). **Added 2026-10-21 (D56):** `respond` chooses its instruction by how many files exist (none: plain chat and code, one: `SCAN`, two: the report), and `ask()`, the API and the page accept 0 or 1 artifact id | medium, 2 lessons, **DONE 2026-10-22** (17.24) |
| 7 | **claims, check, retry** | `extract_claims`; each claim searches B with its own text; one check per claim at the same time; the bounded retry loop (D4); the findings list; a small A merges with the planner (D40) | **heavy**, 3 lessons (all three DONE; lesson 3 in section 24.2) |
| 8 | **the gate** | halt when A and B do not correspond. **DONE 2026-10-30 and its closing review was done on 2026-10-31 (section 28.10); M28 passed (0 wrong halts of 18 matches, 0 wrong FULL of 42; `GATE_VERSION` 1). REDESIGNED 2026-10-29 (D78 to D83, [section 28](../../step2/28-slice-8-gate.md#28-slice-8--the-correspondence-gate-redesigned-on-summaries--decided-2026-10-29)):** ONE function-calling call compares the two SUMMARIES (verdict FULL, PARTIAL or NONE, plus a short reason; unsure means PARTIAL); the planner runs beside it; on NONE a prepared answer made from the two summaries ends the run. No cosine, no threshold for each embedder, no claims needed. The instruction is the main work; a small test M28 (8 to 10 summary pairs) ends the slice, and the instruction may change after it. The summaries and the verdict are stored (D47, D110, built at the start of slice 11) and Jev is tried as the gate in slice 14 (D73 job 2) | medium, 2 lessons (lesson 1 = the design, DONE 2026-10-29, no code; lesson 2 = the build and M28) |
| 9 | **nodes for B alone** | The closing review of slice 8 is DONE (28.10, 2026-10-31); its 3 tests wait to be pasted in. `find_missing` (the claim table read by chunk) and `find_bugs` (a scan of B), then the precision pass for `find_bugs` (D75, test M26). **Also owed here (2026-10-28, D77): redesign and tune the `find_missing` scan, which is a demo version today (section 26.10)** **REDESIGNED 2026-11-03 (29.9, D96 to D103): one node `find_differences` (audit + scan + judge + merge) replaces `check_one` and `find_missing`; `find_bugs` stays separate; 4 lessons (`find_bugs` is not typed yet).** **D106 (2026-11-10, 29.15): `find_bugs` reads only B; A alone is explained with the `REFERENCE` instruction and never hunted (built; its answer is measured with M31).** **M31 (2026-11-09, 29.12): at the end of the slice, measure the prompt id in each finding line (`see B-12`).** **DONE 2026-11-10 (29.17 to 29.20): D104 built (saved findings, whole last answer, the reply says what was reused; follow-ups 7 calls instead of 27), D106 checked on four real files, M31 measured and NOT kept (no gain), the rewrite reads the whole answer, closing review with 16 breaks caught. Next: slice 10.** **Then D104 (moved here 2026-11-09, 29.10): follow-ups get the whole last answer and the findings and claims saved once for each pair of files, with its test M33.** | medium, 4 lessons |
| 10 | **results, the ask-the-user pause and the planner choices (REDESIGNED 2026-11-12, section 31)** | **There is NO `extract_outcomes` node and NO "comparable?" or "does it add up?" node (D108): the answer instruction already has COMPARABLE and the sums, claims already have a `result` kind, and the node was designed from one pair (27.1). Instead: the results measurement is DONE (31.7: the instruction already copes, only the words of COMPARABLE need pinning), the pause that asks the user one question (D109, B) is built and tested in a scratch copy (31.9), and five lessons are designed (31.10).** **FIRST JOB of the slice (added 2026-11-10, S1, 29.21): a timer for each step, and one question run alone, so the time of each step is known.** **UPDATE 2026-11-12: the timer, the server log switch and the scripts are DONE, typed by the user and committed (08d16b4; unit and api 1988 passed, 5 skipped; 29.23). The one-model run of the real agent is in 29.24 (367.6 s against 1,318 s; `find_bugs` and `respond` are 79%); the real chain with the timer is still open.** **At the END of the slice (added 2026-11-08, D105, 29.11): a question about ONE file when TWO are sent. The planner says which file the question is about (A, B or both), and `respond` then answers with `ONE_FILE` and no `find_differences` runs.** **In the SAME planner change (D107, 29.22, moved here from slice 11 on 2026-11-10): the planner also says whether the question needs the files at all (S2: a chat question gets the small CHAT prompt, no parts, no findings; S4) and whether the saved findings answer it or a new check is needed (D104 path b: the question becomes one claim for one audit, or a small hunt on the parts it names, and the new findings are merged into the saved list). Since 2026-11-12 the same planner change also adds the field `ask` (D109): empty, or one short question for the user. One `PLANNER_VERSION` bump and one test of about 10 real questions of each kind for all four (with a count of wrong asks).** | medium, 3 to 4 lessons: the measurement, the `interrupt` toy, B, then the planner change |
| 11 | **routing** | **D110 BUILT 2026-11-15 (31.16). UPDATE 2026-11-16: the chain cleanup (31.17), the measurement of every model (31.19) and, built in a scratch copy, the spreader and one route for each task (31.20, D112 to D116) are done; the repository gets them lesson by lesson, typed by the user.** **FIRST (2026-11-14, D110, 31.13): store the two summaries at ingest and the gate verdict for each pair, and read them in the graph; the gate STAYS after the planner (31.16).** Then: a chain, a `max_tokens` and a thinking level for each node; the chain of `respond` for each plan; the quota-leak test; **and the speed fixes of 29.21: the fast model chain (Flash-Lite) for a chat question, whose choice is made in slice 10 (D107), and a short chain for each finder (S3)** | light, 1 lesson |
| 12 | **the size gate and big repositories** | one `fits(side, budget)` check (D43); the top-N path for claims on a big A; the scan of a big B; claim ranking (D28); the good summary of a big artifact (D46); **(the storage of the summary at ingest MOVED to the start of slice 11 on 2026-11-14, D110; this slice only builds the good summary of D46 and stores it in place of the simple one, and the planner reads the stored summary only if the M5 third arm shows a gain)**; the new test pair. This was slice 9. **UPDATE 2026-10-22: the part size is ONE fixed 12K and the join is a round-robin cut (section 23, D68 and D69).** **Also owed from slice 9 (2026-11-02, 29.8): real measurements of find_bugs on a big repository: the 40K read limit and how files are chosen, the smart cut, the group size, and the cheap trace model.** **Also from slice 9 (D104, 29.10): EXTEND for big repositories the follow-up design that is built at the end of slice 9 (the whole last answer, the findings and the claims saved once for each pair of files, three paths).** **And M32 (2026-11-09, 29.13): rank the finding lines (differences and bugs together) against the question with one cheap Flash-Lite call, against today's fixed rule order.** **And M34 (2026-11-09, 29.14): keep the most important parts of a big B when the prompt cuts it: measure the loss first, then candidates K1 to K8.** | medium, 2 lessons, maybe more **UPDATE 2026-11-14: D110 (the summaries and the gate verdict stored at ingest) moved from this slice to the START of slice 11.** |
| 13 | **measure** | findings against `EXPECTED.md` on the search path (M6; a first small baseline is made at the end of slice 7 and after each slice, D74), the wall clock (M8), M4, M7 and the fix quality (M17). **Also the generalization job (27.1): run every decision of section 27 on MANY pairs, tune on some and test on others, and replace what only fits `quora_siamese`.** **And the tuning job (27.2): every number that is still a guess (A_WHOLE_TOKENS, the budgets, the group sizes, the caps, the votes, the waits and the rest of the table) is swept on many pairs and set from the results.** **And the routing bench (33.5): no waiting for failed calls, no 0.00 / 999.0 cells, at least 5 cases for every cell that can lead a route.** | none |
| 14 | **Jev for decisions** | the decision model `typesafe/jev-1.13` (D73), tried on every job whose answer is a choice or a yes/no, with ONE SCHEMA for each job, against the LLM version that already works (the baseline from slice 13): the gate (8); "are these two numbers comparable?" and "does it add up?" (10; withdrawn for now on 2026-11-12, D108, section 31); `find_missing` (9); the labels of a finding, kind, box, basis and direction (7); the planner's list of steps (M16, 4); "is this follow-up already a full question?" (6, an idea of 2026-10-23). Reranking is done, and the check of a claim is the pilot M15 at the end of slice 7. **All the work on Jev is kept in THIS slice (the user's rule, 2026-10-28): every measurement of it and every code change for it. The check of a claim was measured once in the pilot M15 (25.5: Jev 27 to 29 of 32 claims, 10 to 30 times faster than the LLM checkers, not proven). Slice 14 takes NEW measurements of Jev on the check and on the other jobs. If they agree with 25.5, Jev is added. Other slices put no Jev code in the graph.** | not decided; written when the slice starts |

*(Slice 14 was added on 2026-10-23, so the list has fifteen slices, 0 to 14. The heading of this section keeps its old words so that links to it work. See D73 in section 23.2.)*

**Slice 0 is first because it can change the plan.** If LangGraph is 200MB
resident we write the graph in plain Python instead. Check the gate before the
quality work — the same rule that checked pgvector's 2000-dimension ceiling
before scoring five embedders.

**Parallelism starts in slice 3, not in slice 13.** Generation is 98.2% of a 497-second
answer, so the shape must be proven early rather than bolted on.

**Why this order.** Slice 3 is small and teaches the parallel shape that slices 5, 7 and 9
reuse. Slices 4 and 5 build the new spine (plan, search, merge, respond) before anything is
added to it. Slice 7 needs slice 5 (merge and respond). Slice 8 needs slice 3 only (the
summaries; since D78 it does not need the claims or any score). Slices 9 and 10 need slice 7 (the claim table). Slice 11 needs
the nodes to exist. Slice 12 needs a new test pair. Slice 13 comes last because it measures
all of it.

**Slice 14 comes last.** It needs the LLM version of every node to compare against, and those are measured in slice 13, so nothing waits for Jev (D73). It has no lesson count yet: it is written when the slice starts, with the schema of each job.

**Lessons in all:** 22 for slices 3 to 12 (3 + 3 + 3 + 1 + 3 + 2 + 2 + 2 + 1 + 2), against 13
in the old list. The extra 9 are the nodes the old list forgot (slice 3 grew to 3 lessons on 2026-10-17). Slice 4 grew from 3 to 5 lessons on 2026-10-18 (17.19), so the total is 24.


### 13. ROUTEWAY — probed live 2026-09-29, and what the limits decided

*Raised by the user: section 10.5 recorded Routeway's DeepSeek as working and
nothing ever wired it in, so it was a gap and not a rejection. Probed first with
`scripts/models/probe_routeway.py`, then added on `feat/routeway` (NOT merged).
Exit `91.107.152.24`, AS24940 Hetzner Online, Nuremberg, Google 200. Suite
**839 passed, 5 skipped**, ruff clean; 6 registry mutations and 2 smoke
mutations, every one fires alone. **CHAIN is 54 tiers.***


#### 17.8 The lesson plan for Step 2, and who writes the code — 2026-10-06

**The user writes ALL the code. Claude brings it in the chat.** Claude does not
write files in `labpilot/`. Claude reads files, runs the tests, and runs the
mutation checks (break one line for a moment, put the file back from a COPY, and
tell the user first).

**One lesson** is one short message: the idea in plain words, one tiny example,
then 15 to 40 lines for the user to type. Then the user says "done", Claude runs
the tests, and every file gets its own commit. Lesson size: heavy is 3 or 4
lessons, medium is 2, light is 1, none is a measurement with no new idea. These
are estimates, not promises.

| Slice | What we do | Lessons |
|---|---|---|
| 0 done | does LangGraph fit 512 MB (yes, about 55 MB) | none |
| 1 done | the speed of each of the 56 models | none |
| **2 (DONE 2026-10-14: lessons 1 to 4 and the closing review, 17.14)** | replace `ask()` with a graph that gives the same answer, and add chat memory (checkpointer + `thread_id`) | **heavy, 4** |
| 3 | `summarize` for A and for B at the same time (two independent steps run together) | medium, 3 |
| 4 | the planner: one call chooses the steps and writes the queries. **Preceded by a small lesson on function calling (D34)** | medium, 5, **DONE 2026-10-19** (17.19, 17.20) |
| 5 | run the plan: a search for each query at the same time, merge and remove duplicate chunks, the final `respond` node | **heavy, 3, DONE 2026-10-21** (17.22, 17.23) |
| 6 | follow-up questions: rewrite them into standalone ones, and `respond` for 0, 1 and 2 files | medium, 2, **DONE 2026-10-22** (17.24) |
| 7 | the loop: claims, check each one, search again at most 2 times | **heavy, 3** |
| 8 | a step that can STOP the graph (the gate: one call on the two summaries, D78, section 28) | medium, 2 |
| 9 | the nodes for problems in B alone: `find_missing` and `find_bugs` | medium, 2 |
| 10 | results and the ask-the-user pause, and the planner choices of D107 (REDESIGNED 2026-11-12, section 31) | medium, 3 to 4 |
| 11 | each step gets its own models, token limit and thinking level | light, 1 |
| 12 | the size gate and big repositories (was slice 9) | medium, 2 |
| 13 | score the findings against the answer key and time the run | none |
| 14 | Jev for decisions: the decision model on the jobs of D73, one schema for each job (added 2026-10-23). **All the work on Jev is kept in THIS slice (the user's rule, 2026-10-28): every measurement of it and every code change for it. The check of a claim was measured once in the pilot M15 (25.5: Jev 27 to 29 of 32 claims, 10 to 30 times faster than the LLM checkers, not proven). Slice 14 takes NEW measurements of Jev on the check and on the other jobs. If they agree with 25.5, Jev is added. Other slices put no Jev code in the graph.** | not decided |

**The 4 lessons of slice 2:** (1) state, node and edge, with a graph of 2 steps;
(2) a list that grows, with a reducer; (3) chat memory: the checkpointer and the
`thread_id`; (4) cut `ask()` into steps that receive their functions from `api/`.

**How a new session continues (updated 2026-10-22):** slices 0 to 6 are DONE. Read the Phase paragraph of Current Status and the last section of 17 (17.24), check git (branch, status, `git log -5`), and continue with slice 7 (claims, check, retry; D4, D39, D40). The prompt that the last session gave the user is the best start (Working Rules, "Review pass after every slice, and a hand-off prompt at the end of every session"). **Two rules the user set (17.13) still hold: they type ALL product code
(only tests are copy-paste), and a step is given WHOLE in one message.** Lessons call no model, so
the exit-ISP check is not needed until the first live test. The chat tables must exist in the
database the app uses: run `python -m scripts.setup.setup_checkpoints` once from the repository root
(17.14). Since 2026-10-14 that script also locks the four tables (17.15). **The lesson scripts named
in 17.9 to 17.13 as `scripts/<name>.py` now live in `examples/langgraph/`.**


#### 17.11 Lesson 3 was taught, 2026-10-08

**Status: taught on 2026-10-08 and DONE on 2026-10-09.** The user typed
`scripts/graph_with_memory.py` (not the planned name `lesson3_memory.py`), ran it, and it was
committed alone (`df1331e`, `ruff check` and `ruff format --check` pass). The output was right:
call 2 says `seen 1`, call 3 says `seen 0` (chat-8 is a new thread), and `get_state(chat7)` holds
both questions. The user printed the whole `StateSnapshot` (no `.values`), which also shows a
`checkpoint_id` per saved copy and a `parent_config` that points to the previous copy: that is the
list D22 will have to trim.

**What went wrong in the user's first run, and what was taught from it** (do not re-teach):

- Their `State` still had the key `findings`, copied from lesson 2, while the node read
  `state["history"]` -> `KeyError: 'history'`. Their second mistake: `"history": [state["history"]]`
  where it must be `[state["question"]]`. They fixed both alone after one message.
- **Input is a partial state.** `invoke` does not need every key. LangGraph merges the input into
  the saved copy of the thread. Lessons 1 and 2 sent every key only for clarity, not because it is
  required (tested: lesson 1 works with only `question`, lesson 2 works with `{}`). A `TypedDict`
  is not checked when the program runs; only a type checker such as mypy looks at it.
- **The rule for reading a key:** a node can read a key only if the key has a value at that
  moment. A key gets a value from four places: (1) the input we send, (2) an earlier node, (3) the
  saved copy of the chat, (4) a reducer, which starts the key as an empty value of its type
  (`[]` for `list[str]`). If none applies: `KeyError` (tested with `chunks` and with `history`
  without the reducer). **I first stated this rule with only three places and the user caught the
  hole** (call 1 reads `history` that nobody sent). Check a rule against the exercise before teaching it.
- **`config` is not state.** `thread_id` tells LangGraph which saved copy to load, like
  `WHERE chat_id = 'chat-7'` tells Postgres which row to read. It is not a column of the row.

**What was taught** (the four labelled parts: concept, details, math, where it sits):

- Until now the state lived only during one `invoke`. A **checkpointer** saves a copy of the
  state after every node (like `torch.save`, but automatic). A **`thread_id`** is the name of
  one chat (like a primary key). The same name loads the latest saved copy; a new name starts
  empty.
- `compile(checkpointer=...)` turns saving on. `thread_id` is NOT a key of `State`: it goes
  in `config={"configurable": {"thread_id": "chat-7"}}`. (The user mixed these up in lesson
  1, see 17.9.)
- At the start of a call LangGraph loads the latest copy of that thread, then applies the new
  input with the SAME rules from lesson 2 (`question` replaces, `history` adds).
- The math: `s^c_t = run(r(s^c_{t-1}, u_t))` and `s^c_0 = empty`. `c` is the `thread_id`, `t`
  the message number, `s` the saved state, `u` the new input, `r` the rule of each key.
  Different `c` never mix.
- Today `InMemorySaver` (the copies live inside the Python process and are lost on restart).
  Later the Postgres saver in the same Supabase database (D19, lesson 4).

**The exercise.** State: `question: str`, `history: Annotated[list[str], operator.add]`,
`answer: str`. One node `respond` returns `answer` (it says how many earlier questions it has
seen) and `history: [state["question"]]`. Compile with `InMemorySaver()` from
`langgraph.checkpoint.memory`. Calls 1 and 2 use `thread_id` `chat-7`, call 3 uses `chat-8`,
then print `graph.get_state(chat7).values`. Claude ran a reference copy (it is not in the
repo): the answers say "seen 0", "seen 1" and "seen 0", and `history` of chat-7 holds both
questions. `history` needs no initial value when the key has a reducer. Claude's reference
file passes `ruff check` and `ruff format --check`.

**Next, lesson 4:** cut `ask()` into steps that receive their functions from `api/` (D7), swap
the in-memory saver for the Postgres saver, and add `thread_id` to the compare request and
response (D17). Before that, check `langgraph-checkpoint-postgres` (D19: package name and
version, works with `psycopg 3.2.12`, works on the session pooler at port 5432) and how to
keep only the latest copy of each chat (D22).


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

**Process notes.** The popup question about the branch (the AskUserQuestion tool) was declined by the user, so the branch question was asked in plain text, and then the app quit; Claude continued from git, which had not changed. Claude does NOT commit: the user committed the toy file and asked Claude only to write these notes. Claude wrote them to CLAUDE.md and DETAILS.md in the same session (the two-file rule). Git: `feat/plan-to-run` was made by the user from `main` at `0ac80d4`; Claude suggested a NEW branch from `main` and not `feat/planner`, because `feat/planner` is 47 commits behind `main` (they split at `08a355d`) and holds slice 4 as 6 older commits. Whether the new branch is pushed was not checked.

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
