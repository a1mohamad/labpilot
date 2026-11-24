# Section 29.21 to 29.24: speed and the timer

[Docs home](../README.md)

#### 29.21 Speed: what the end of slice 9 showed, and the four fixes planned (2026-11-10)

*Written at the user's request after one first question took 1,318 seconds and 37 model calls (M33, OTP pair), and a follow-up "What is HMAC?" still took 226 seconds and 7 calls. Big chat products answer in about a second because they use paid fast models, stream the first words, make one call for a simple question and send a small prompt (29.21 is about what LabPilot can change).*

**What is known and what is not.** The run records no time for each step, so nobody can say which step is slowest. The log showed two bug-hunt calls where all 108 tiers failed ("no tier answered list_defects", "no tier answered answer_checklist"), each spending up to its 300-second limit (D102), and several rate-limit waits. Two measurements ran at the same time on LiteRouter, which takes one request at a time for the whole account, so the number is a worst case.

| # | fix | when | what done looks like |
|---|---|---|---|
| **S1** | **A timer for each step.** Every node (rewrite, plan, the summaries, gate, measure, the searches, merge, claims, find_differences, find_bugs, final merge, respond) writes one log line with its seconds, and each model call with its tier and seconds. Then one question is run ALONE, with nothing else on the providers, and the split is written down | **the first job of slice 10** (before M8, which is the full measurement in slice 13) | a table of the seconds of each step for one first question and one follow-up, on two pairs |
| **S2** | **A fast path for a question that needs no file** ("What is HMAC?", "thank you"). The planner says the question needs no file parts; then the answer uses the small CHAT prompt on a fast model (Flash-Lite), no parts, no findings, no summaries in the prompt | **the choice: end of slice 10 (D107, 29.22); the fast model chain: slice 11** | such a question answered in a few seconds; a test that its prompt holds no parts |
| **S3** | **The bug hunt walks the full chain.** When the good tiers are spent or busy, one call walks all 108 tiers and can burn its whole 300 seconds for nothing. Give `find_bugs` (and every finder) a SHORT chain of tiers that fit its group size and answer tool calls, and stop early when they are spent | slice 11 | no finder call walks more than about 10 tiers; the time of a failed call is a few seconds, not minutes |
| **S4** | **Saved findings are added to every follow-up** by `with_saved_steps` (D104), even to a question about something else. They cost no model call, but they make the prompt bigger and the answer slower. Add them only when the plan or the question needs them (the planner decides, or S2 skips them) | **end of slice 10, with S2 (D107)** | a chat question on a saved pair sends no finding lines |

Also related and already planned: routing for each node (slice 11), M8 (slice 13), streaming the answer to the page (SSE, Step 3).

#### 29.22 One planner change for four choices (D107, decided 2026-11-10; the fourth, `ask`, added 2026-11-12; for the end of slice 10)

*Talked through with the user right after slice 9 closed. Nothing is built.*

**What D104 already does.** With the same files and the same instruction versions, the claims, differences and bugs are read from `saved_results` and nothing runs again. A new file has a new id, so its key is new and the full analysis runs; a file stored again loses its old rows; a new instruction version gives a new key. (Running a step again would NOT give the same words: the models do not repeat themselves. The reasons to save are that claims depend only on A and the version, and that a second run costs minutes and makes duplicates.)

**What is missing is a choice about the question:** (b) the question needs a NEW check (today it is answered from the saved findings and a normal search only), and (c) the question needs no file (today it still gets the saved findings, the search and the two-file format, so "What is HMAC?" took 226 s).

| # | decision |
|---|---|
| **D107** | **The planner makes four decisions about the question in ONE change, at the end of slice 10 (the fourth was added on 2026-11-12):** (1) which file it is about, A, B or both (D105); (2) whether it needs the files at all (S2, S4: a chat question gets the small CHAT prompt, no parts, no findings, no summaries); (3) whether the saved findings answer it, or a new check is needed (D104 path b: the question becomes one claim for one audit, or a small bug hunt on the parts it names, and the new findings are merged into the saved list with the merge that removes repeats); (4) whether to ask the user one short question before `respond` (the field `ask`, D109, section 31). An unclear answer counts as the safe side (both files; files needed; saved findings plus a normal search; NO question, because a missing question only makes the answer a little less exact, while a wrong pause wastes the user's time). The reply says which path ran ("answered from the earlier analysis" or "checked again"). The fields are checked in code (D50), `PLANNER_VERSION` goes up ONCE, and ONE test of about 10 real questions of each kind, on two tiers, measures all four choices (how often the planner chooses right, how often it asks when it should not or stays silent when it should ask, the seconds and calls, faults read by hand). Slice 11 keeps only the fast model chain for a chat question (routing) and S3 |

**Why there and not now.** The four are the same kind of decision and D105 already changes the planner at the end of slice 10, so the planner changes and is measured once. The S1 timer, the first job of slice 10, shows how much time path (c) really wastes before it is fixed. Slice 9 tested only 5 real follow-ups, too few for a choice that can be wrong. **The cost of waiting:** until then a chat question stays slow and a new question gets no fresh check.

#### 29.23 S1 is built and checked in a scratch copy: the timer (2026-11-11)

*Built and tested by Claude in the scratch copy `s12`. The user then typed it into the repository and it is committed as 08d16b4 (23 files; checked again on 2026-11-12: unit and api 1988 passed, 5 skipped, `ruff` clean).*

**What it is.** Two clocks, written as log lines on the logger `labpilot.timing`, with the numbers also in `record.timing` (a dict) for scripts:
- **the step clock:** every graph node is wrapped by `timed(name, node)` (in `graph.py` through one helper `add(name, node)`), and writes its name, start, end and seconds;
- **the call clock:** `LLMClient.generate` writes one line for each call: the step that made it, the tool, the tier and model that answered (or none), the seconds, and how many tiers failed first.

A call must know its step. The step name is kept in a *context variable* (a variable whose value belongs to the current piece of work). A new thread starts with an empty context, so every thread-pool job in `api/` is wrapped by `in_this_context(...)`. LangGraph's own threads keep the name by themselves (tested on LangGraph 1.2.12). A test reads the `api/` source and fails if a `pool.submit` or `pool.map` job is given without the wrapper.

**Files (scratch copy).** `labpilot/timing.py` (new, in the SHARED layer, so `test_architecture.py` lists `timing`), `agent/graph.py`, `llm/chain.py`, `api/tool_calls.py`, `api/claims.py`, `api/difference_finder.py`, `api/bug_hunt.py`; `scripts/timing/time_one_question.py` (runs a real question, prints the steps, the calls grouped by step and tool, and the chain of steps that decided the wall clock); tests `tests/unit/test_timing.py`, `tests/unit/agent/test_graph_timing.py`, `tests/unit/test_time_one_question.py`.

**The server log switch.** The app never configured logging, so INFO lines (the new ones and the old ones) are hidden in a running server. The environment variable `LABPILOT_LOG=info` now turns on the INFO lines of the `labpilot` loggers only (`configure_logging` in `api/main.py`, `ApiConfig.LOG_LEVEL`, a line in `.env.example`, `tests/api/test_logging_switch.py`). It is off by default.

**Checks.**
- Unit and api tests in the scratch copy: 1984 passed, 5 skipped; `ruff check` and `ruff format --check` clean.
- Deliberate breaks: 16 on the timer and 9 on the script's reading rules, all caught after one fix. One survived first: a step whose end time equalled its start time. The test used `approx` on clock times of about 1.7 billion, where "close" means thousands of seconds; it now compares the distance and sleeps 0.05 s.
- **Calibration against a clock I control** (no model, no network): a fake graph whose nodes sleep for known seconds. The expectation was worked out from the sleeps before the timer was read: plan 2.0, summaries 3.0 and 1.0 (together), stuff 0.5, respond 2.5, so at least 6.0 s. The timer said 2.001, 3.001, 1.000, 0.501, 2.500; the outside stopwatch (`perf_counter`, never used by the timer) said 6.018 s; the chain of steps was named correctly.
- **A real run on a tiny pair** (a short spec and a short Python file, read whole), the chain as shipped, VPN exit AS212238 Datacamp Amsterdam, Google probe 200. A second, independent clock was added around every HTTP request (`perf_counter`, with the thread that made it), and the rules were about intervals that must fit inside each other, because the timer and the HTTP clock measure different boundaries. Result, all rules held: the outside stopwatch and the timer's wall differ by 0.006 s of 210 s; every HTTP request lies inside a step; every call ends within 0.004 s of its last HTTP request; the timer's call end and my wrapper's agree to the millisecond; a step with one call is at least as long as that call (plan 33.12 against 32.24, gate 18.86 against 18.86, respond 132.40 against 132.40). **The timer is right to within a few milliseconds.**

**What the tiny run also showed (one run, one tiny pair, so a hint and not a result):**
- the answer took 210 s for a pair that fits in a few hundred tokens; **respond alone took 132 s** (GLM-5.3 Flash on LiteRouter); the planner took 33 s; one summary 39.6 s after two failed tiers and a wait of 15.6 s before its first HTTP request (LiteRouter's 8 s gap and a retry), while the other took 12.5 s;
- **18.1 s (9%) were spent after the last step**: the chat save and the prune over the VPN. It is the largest time that no node owns. Not yet split into save and prune;
- `rewrite` took 0.0 s on a first question (no history), as expected.

**What was NOT done.** The long run of the real pairs (OTP twice, quora) was started and stopped by the user's decision: the timer needed a short check, and the long run answers a different question (where the 1,318 s of M33 go). It is still open. The pure cost of each node on each single model (no chain) is built as a script (`node_cost.py`, in the session scratch folder) and dry-tested; it has not run.

**The 7 old integration tests** in `tests/integration/test_api_over_the_chain.py` fail in the repository (they fail the same way on the committed tree): since D104, `SavedResults` calls `conn.execute(...)` and these tests hand it a fake connection `object()`. Fixed in the scratch copy by stubbing `labpilot.api.saved.read_saved` and `write_saved` in the test's setup (two lines of patching and a comment); the 7 tests pass. The slice 9 closing review had not run the whole suite, which is why it went unnoticed.

#### 29.24 The pure time of every node: our agent with ONE model for each chain kind and no fallback (2026-11-11)

*Why. The step seconds of a normal run include fallbacks (a dead tier is tried first), retry waits and pacing. The user's hypothesis was that the 1,318 s of M33 came from the chain and its fallbacks, not from the nodes. This run takes the chain away: the real agent, on a real pair, with exactly one tier for every call. It was run in the scratch copy `s12`; nothing is in `labpilot/` for it.*

**How it works (a harness in the session scratch folder, `onemodel.py`).**
- Every `LLMClient.generate` of the product is rerouted to a client whose chain is **one tier, no retry** (`max_retries_per_tier=0`). The tier is the FIRST live tier of the chain that the call asked for (the full chain, `for_claims`, `for_trace`, `for_skeptic`), because the chain-first tier is the model the product means to use. A table of overrides replaces a model that does not work, for all calls of that chain kind or for one step only (`"find_bugs|GLM-5.3 Flash (LiteRouter)"`). Google models rotate over the three keys, which is the same model on three quotas.
- The search path is forced (`fits_whole` always answers no), the worst case: the planner, the summaries, the gate, the searches, the merge, the claims, `find_differences`, `find_bugs`, `final_merge` and `respond` all run. One real pair: the RFC 4226 and RFC 6238 text as A and the Go repository `pquerna/otp` as B (the OTP pair of slice 9; in M33 it was already on the search path, so forcing the search changes little here, and it keeps the run the worst case for any pair).
- A failed call is recorded with its step, tool, model and error, and the run goes on. (The first version stopped at the first failed call; one malformed answer then hid the slow nodes after it. It was changed after attempt 3.) The stored files are kept in a schema, so a rerun does not ingest again.
- The timer of 29.23 and an independent HTTP clock ran beside it.

**What happened, attempt by attempt.**

| attempt | models | result |
|---|---|---|
| 1 | chain-first everywhere (GLM-5.3 Flash on LiteRouter for the full chain and the skeptic) | ended in 30 s: LiteRouter answered `403 Too many concurrent requests` to the second summary (one request at a time for the account) and closed the planner's connection; the database connection also dropped once (`SSL SYSCALL EOF`, the VPN) |
| 2 | GLM on LiteRouter replaced by **DeepSeek V4.1 Flash on OrcaRouter** | ran everything up to the bug hunt in 160 s; DeepSeek returned an **empty answer** to `list_defects` after about 85 s, and the first-failure rule ended the run |
| 3 | the bug hunt moved to **Gemini 3.6 Flash** | ended after 53 s: a Flash-Lite answer without the `quote` field (and a 503 before it) |
| 4 | the same, and failures no longer end the run | **complete: 367.6 s, 37 model calls, 5 failed calls** (4 Google 503 "high demand", 1 malformed claims answer) |

**Attempt 4: the timer's own table.** VPN exit AS212238 Datacamp Amsterdam, Google probe 200. `*` is on the chain of steps that decided the wall clock (362.4 s of steps; the rest is 0.2 s before the graph and 5.0 s after it).

| step | model | starts | seconds |
|---|---|---|---|
| plan * | DeepSeek V4.1 Flash (OrcaRouter) | 0.2 | 14.7 |
| summarize_a, summarize_b (beside the plan) | DeepSeek | 0.2 | 6.3, 6.0 |
| gate * | Flash-Lite 3.5 | 14.8 | 6.8 |
| measure * | none | 21.6 | 0.4 |
| search_one x7 (together) * | embeddings and the database | 21.9 | 10.8 to 15.5 |
| merge * | the real rerank chain (it calls providers directly, so it was NOT rerouted) | 37.5 | 7.3 |
| extract_claims * | Flash-Lite 3.5 (11 calls, 4 at once) | 44.8 | 26.3 |
| **find_bugs** * | Gemini 3.6 Flash, Flash-Lite 3.1 for the trace | 71.1 | **142.1** |
| find_differences (beside find_bugs) | Flash-Lite 3.5, one merge on DeepSeek | 71.1 | 48.8 |
| final_merge * | Flash-Lite 3.5 | 213.2 | 3.3 |
| **respond** * | DeepSeek V4.1 Flash (OrcaRouter) | 216.5 | **146.1** |
| remember * | none | 362.6 | 0.0 |

**What the numbers say (one run; the readings marked "inferred" are mine, not measured):**
- **367.6 s against 1,318 s in M33, with the same number of model calls (37).** The nodes themselves are fast; the first six steps (plan, summaries, gate, searches, merge) end at 44.8 s.
- **Two steps are 79% of the wall clock: `find_bugs` 142 s (39%) and `respond` 146 s (40%).** Claims are 26 s (7%), the gap after the graph is 5.0 s (1.4%).
- Inside `find_bugs` the longest call of each group adds up to the step: the two checklists (52.5 s), then the audit (44.2 s), then the skeptic (44.5 s) are 141.2 s, against 142.1 s. They depend on each other (the checklist feeds the audit, the audit feeds the skeptic), so they cannot run at the same time. *Inferred from the sums; the call windows were not drawn.* `find_differences` took 48.8 s and runs beside it, so it is free as long as `find_bugs` is the longer one.
- `respond` is one call of 146 s on DeepSeek V4.1 Flash. The tiny-pair run of 29.23 had 132 s on GLM-5.3 Flash for a few hundred tokens of input, so the long answer is not caused by the prompt size alone. *Not tested: the same report on another model.*
- The 5 s after the graph (chat save and prune) was 18 s in the tiny run of 29.23, so it varies; both are single samples.

**What this does and does not show.**
- It supports the hypothesis, it does not prove it. M33 differs in more than the chain: a different moment of the providers, Cline's GLM-5.3 gone, two measurements running at once, and no timer. The real chain on this pair, measured with the timer, was **not run** today; that run would show how much of the 1,318 s is fallbacks and waits. It is still open.
- This is one run of one pair on models chosen after three failures. Four of the five failed calls are Google 503s, which a chain would have retried. Failed calls left a few claims and findings missing, so the nodes after them had slightly less input than in a perfect run.
- Nothing here scores quality: DeepSeek writing the report and Flash-Lite writing the claims were not compared with other models.
- OrcaRouter allows 50 requests a day; the four attempts used 17.

**The cross-check of the timer on this run (seven rules, all about intervals that must fit inside each other):** all hold. The outside stopwatch and the timer's wall differ by 0.033 s of 367.6 s, and **that gap is my own rounding**: I typed the wall as 367.6 from a line printed to 0.1 s, and the real value is 367.57; the first reading of "BAD" was my expectation, not the timer. Every HTTP request is inside a step; every call ends within 0.007 s of its last request; the timer's call ends and mine agree to the millisecond; a step with one call is at least as long as that call (plan 14.67 against 14.00, gate 6.75 against 6.75, respond 146.07 against 146.07). There were no waits of more than a second before a first request, because the one-tier client has no retry and no pacing for these providers.

**Model facts learned on the way.**
- LiteRouter cannot take parallel calls (403 "Too many concurrent requests"), so it cannot lead a chain whose nodes fan out (already in 30.7; now seen with the product's own nodes).
- DeepSeek V4.1 Flash on OrcaRouter answered `list_defects` with an empty answer once (attempt 2), and worked for the plan, the summaries, one merge and `respond`. **Retested the same day (4 calls: the two saved whole-file bug-hunt prompts, 2 times each, straight to the provider, raw reply kept):** 2 answered (31.5 s and 59.0 s, `finish_reason=tool_calls`, a good tool call), and **the empty answer did not come back (0 of 4)**. The other 2 failed with a **dropped connection** (`RemoteDisconnected` after 29.6 s; `SSL EOF` after 35.2 s). The model thinks a lot and not evenly: 2,787 and 7,470 reasoning tokens against a 12,000 limit on output, so a longer chain of thought could use the whole limit and leave no answer; that would explain the empty answer, but **it was not shown**. So the failures seen so far are of two kinds: an empty answer (once) and a closed connection (twice in four), and the only certain thing is that the provider is flaky on long calls through this VPN exit. OrcaRouter requests used today: about 21 of 50.
- Gemini 3.5 Flash-Lite, 3.1 Flash-Lite and 3.6 Flash gave 503 "high demand" five times in 37 calls.

**Open.** The real chain on this pair with the timer (to split the 1,318 s into fallbacks, waits and work); the same nodes on other models (`node_cost.py`, not run); a second pair; whether the `find_bugs` order (checklist, audit, skeptic) can be shortened; the report on a faster model.
