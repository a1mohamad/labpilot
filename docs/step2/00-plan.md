# Step 2: the plan (sections 0 to 7)

[Docs home](../README.md)

## STEP 2 — the plan, recorded 2026-09-22

*Session 27 wrote no source on purpose, and the plan below is not the one the
session started with. The user refused three of my framings in a row and was
right each time, so most of what follows came out of research rather than out
of this file's existing design notes. Sources are named; each finding carries
how strong it is.*

**No ISP probe was needed: nothing here called a model.**

### 0. Why the research happened at all

The session opened by teaching what an agent is, and the plan was to build
`extract_claims` as the front door: turn side A into ~14 claims, and search
with those instead of with the user's question. The user rejected it:

> *"it doesn't make any sense for me to convert any question to fixed 14
> queries... user question may vary too much... i want to know what pro do?"*

That objection is correct, and checking it overturned part of this file.

### 1. THE RESEARCH — twelve findings, with their strength

| # | finding | strength |
|---|---|---|
| **F1** | **Dense retrievers COLLAPSE on reasoning questions.** `SFR-Embedding-Mistral` scores **59.0 on BEIR** and **18.3 nDCG@10 on BRIGHT** | ✅ peer-reviewed benchmark |
| **F2** | Letting an LLM reason about the query **before** retrieving is worth **+12.2 nDCG** on BRIGHT | ✅ published |
| **F3** | Rewriting a GOOD query can HURT: **-10.8 NDCG@5** when HyDE is stacked on a query-trained encoder | ✅ published |
| **F4** | Multi-query **lost to naive RAG** in the ARAGOG benchmark | ✅ published |
| **F5** | The 2026 production pattern is **agentic search** — the model writes its own queries, in a loop | ⚠ vendor docs + blogs |
| **F6** | **Claude Code has NO vector index.** grep, glob and file reads, chosen turn by turn, so it always works from live code rather than a snapshot | ⚠ third-party writing, not Anthropic's own docs |
| **F7** | Agentic keyword search reached **over 90% of RAG-level performance with no vector database** (Amazon Science, Feb 2026) | ⚠ reached us through a blog, not the paper |
| **F8** | **Exact match beats semantic search on well-named code.** Cursor's own figure for semantic search is **+12.5%** over keyword | ⚠ blogs |
| **F9** | **Plan-and-execute beats ReAct** where the structure is knowable: **92% vs 85%** completion, **$1.24 vs $2.87**, **38.6K vs 47.2K** input tokens. ReAct wins on SHORT tasks; plan-and-execute wins on long tasks with parallel steps | ⚠ one 2026 benchmark |
| **F10** | For mixed providers the recommended shape is **structured output, with a text-parse fallback** | ⚠ guidance |
| **F11** | **Over 60% of multi-turn follow-ups** carry unresolved pronouns, so decontextualization is near-universal in production | ⚠ one production study |
| **F12** | Agentic retrieval loops need a **hard search budget** or they loop forever | ⚠ guidance |

**F1 is the one that settles the argument this session was about.** The same
model scores 59 on ordinary lookup questions and 18 on reasoning questions.
*"Why do the results diverge?"* is the second kind. So the instinct *"a modern
embedder handles a raw question, so it will handle ours too"* is exactly what
the benchmark disproves — and the fix that works on BRIGHT is F2, reasoning
before retrieval.

Sources: BRIGHT (arXiv 2407.12883, and the reproducible-baselines paper
2509.02558) · *Not All Queries Need Rewriting* (2603.13301) · ARAGOG
(2404.01037) · *ReAct vs Plan-and-Execute* (atlan.com, dev.to) ·
*Structured Outputs vs Function Calling* (machinelearningmastery.com) ·
Claude Code indexing (vadim.blog) · Cursor indexing
(towardsdatascience.com) · *Agentic RAG Needs a Search Budget* (hackernoon).

### 2. NINE DECISIONS

| # | decision |
|---|---|
| **D1** | **Step 2 is PLAN-AND-EXECUTE as the main shape, and ReAct is used in exactly ONE place (D4).** *(Clarified 2026-10-08: the old wording "not ReAct" misled the user. The design is a mixture with the focus on plan-and-execute. See [19.1](19-design-decisions.md#191-plan-and-execute-and-react-together-d1-clarified).)* This confirms the existing LangGraph choice — but it was taste before and it is evidence now (F9). LabPilot is report generation with a knowable structure and independent, parallelizable steps, which is the exact case the benchmark gives to plan-and-execute |
| **D2** | **THE PLANNER WRITES THE QUERIES**, from the user's question. Queries are NOT fixed. `extract_claims` stops being the front door and becomes ONE node the planner may choose *(clarified 2026-10-14, [D39](21-final-design.md#212-decisions): claims stay as a safety net for questions with A and B, and a small A merges the planner and the claim call)* |
| **D3** | **REVISED BY D13 — read that first.** *(Fixed 2026-10-08: this row used to say "STRUCTURED OUTPUT, not function calling", which was the OLD decision.)* The asking channel is **FUNCTION CALLING first, with first-valid-JSON parsing as the fallback**, for every node whose output code reads. Nodes that write prose for a person use plain text. Scope and table: [19.3](19-design-decisions.md#193-where-function-calling-is-used-d13-scope--d29) |
| **D4** | **Exactly ONE ReAct loop**: re-search when `verify` reports *not found*. **Max 2 retries**, against a budget (F12) |
| **D5** | A **decontextualization node** for turn 2 onward, rewriting a follow-up into a standalone query (F11) |
| **D6** | A **specific** user question goes to search **RAW**. Do not rewrite it (F3) |
| **D7** | `agent/` is **CORE**, so it may not import `llm/`, `store/`, `embed/` or `rerank/`. Nodes take **injected callables** |
| **D8** | **CANDIDATE, not committed:** an exact-match / symbol lookup tool beside vector and BM25 (F6, F7, F8) |
| **D9** | Graph state needs **reducers**: `findings` and `attempts` APPEND, everything else replaces |

#### D2, and why the shape the user asked for is the right one

The user described it before it had a name:

> *"if our system was good, it must create 14 different queries based on the
> question user ask... its kinda like what the UI sent in agents like claude
> code or even chatbots like chatGPT."*

That is plan-and-execute with structured output. One cheap call reads the
question plus a map of what the artifacts contain, and returns JSON:

```
IN    the user's question + a per-file map of A and B

OUT   {"nodes":   ["extract_claims", "verify", "explain_divergence"],
       "queries": [{"side": "B", "text": "gradient clipping global norm"},
                   {"side": "B", "text": "learning rate schedule and warmup"}]}
```

Three different questions produce three different plans, which is the whole
point:

```
"why are my results diverging?"   claims + verify + outcomes + explain
"why did the paper get that?"     summarize A + the result claims of A. B barely touched
"what is wrong in my code?"       claims + verify + find_bugs
```

#### D3, and why it is not the weak option

`rerank/` already proves the mechanism: `api/reranking.py` sends Gemini a
`responseSchema` for an integer array, and that one setting took gemma from
**45.5s to 14.4s** and stopped the reply being prose wrapped around an answer.
The planner is the same trick one level up.

Function calling is the tidier protocol and is what a single-provider product
should use. It is wrong HERE for a specific reason: **the chain falls back
across 40 tiers, and a tier without a `tools` field does not answer worse — the
request shape is invalid and the call fails.** Fallback is the thing our chain
exists for. It would also mean changing `_payload` and `_extract_message` on
every provider, plus a new contract, in the most heavily tested layer we have.

**Which tiers actually support function calling is UNVERIFIED** and is M3
below. Gemma is not a Gemini model and its feature set differs.

#### D7, found by reading our own test rather than by design

`tests/unit/test_architecture.py` line 12 already classifies `agent` as core,
and core may import only shared and core. So the first node that calls
`LLMClient` directly turns the build red.

That is not an obstacle, it is the shape `rerank/` already solved:
`LLMReranker` takes a `complete` callable instead of a provider, and the entry
layer wires it. Nodes take the same treatment:

```
generate(prompt, max_tokens) -> str
retrieve(side, query)        -> chunks
rank(query, documents)       -> order
```

Two things this buys: `api/` stays the only wiring place, and **every node is
testable with no provider, no quota and no network.**

### 3. FIVE CORRECTIONS

| # | what was wrong |
|---|---|
| **C1** | *"Most embedders are trained only on (sentence, similar sentence) pairs"* — **false.** Modern retrieval embedders are trained on BOTH symmetric and asymmetric data. That is exactly WHY the `task` flag exists: a model that knows both relations has to be told which one you want |
| **C2** | Framing `extract_claims` as *query rewriting* — **wrong.** It reads side A and never touches the user's question. The published negative results about rewriting (F3, F4) are about a different operation |
| **C3** | **"13 of 19" says nothing about retrieval.** See below — it is the worst of the five |
| **C4** | *"The user's question is never the search query"* is **TOO STRONG.** True for the default prompt, which carries no content at all. False for a specific question, where F3 says rewriting is likely to HURT |
| **C5** | The status block said Jev was on `feat/jev-probe` and not merged. `git diff --stat main feat/jev-probe` is **empty** — it is on `main` |

#### C3 — NO FINDINGS SCORE HAS EVER BEEN MEASURED ON THE SEARCH PATH

Every findings number in this file — 10, 11 and **13 of 19** — was produced
with the corpus **STUFFED**. Read from the saved run:

```
artifacts/2026-08-17_04-36_report-stuffed_medium.md
    chunks sent: 96 of 96
```

Retrieval did not run, so the query was not a variable and the number is not
evidence about it either way.

And the runs that DID send partial context are worse than useless for this:

```
21 scored runs carry a chunk count
  9 at 96 of 96        stuffed
 12 at 60-65 of 96     the DUMB POSITIONAL SELECTOR
 every partial run is dated 2026-08-14 to 08-16
```

pgvector did not exist until 2026-09-04 and `ask()` until slice 7. So every
partial run predates vector search entirely, and used the throwaway 50/50
selector that slice 7 deleted.

> **The whole findings record describes a path we do not ship.** Step 2's
> baseline therefore has to be measured before Step 2 can be said to beat
> anything — M6 below.

### 4. THE SLICES — fourteen since 2026-10-14 (nine before)

*(Eight until 2026-10-07, nine until 2026-10-14. On 2026-10-14 the user saw that the nine
slices did not build most of the nodes the capability library promises (`summarize`,
`find_missing`, `find_bugs`, the final `respond` node and others), and the list was rewritten
together. The reasons, the new decisions D39 to D44 and the map from every planned node to its
slice are in [section 21](21-final-design.md#21-the-final-design-and-the-new-slice-list--agreed-2026-10-14).
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
| 8 | **the gate** | halt when A and B do not correspond. **REDESIGNED 2026-10-29 (D78 to D83, [section 28](28-slice-8-gate.md#28-slice-8--the-correspondence-gate-redesigned-on-summaries--decided-2026-10-29)):** ONE function-calling call compares the two SUMMARIES (verdict FULL, PARTIAL or NONE, plus a short reason; unsure means PARTIAL); the planner runs beside it; on NONE a prepared answer made from the two summaries ends the run. No cosine, no threshold for each embedder, no claims needed. The instruction is the main work; a small test M28 (8 to 10 summary pairs) ends the slice, and the instruction may change after it. The summaries and the verdict are stored (D47, D110, built at the start of slice 11) and Jev is tried as the gate in slice 14 (D73 job 2) | medium, 2 lessons (lesson 1 = the design, DONE 2026-10-29, no code; lesson 2 = the build and M28) |
| 9 | **nodes for B alone** | `find_missing` (the claim table read by chunk) and `find_bugs` (a scan of B), then the precision pass for `find_bugs` (D75, test M26). **Also owed here (2026-10-28, D77): redesign and tune the `find_missing` scan, which is a demo version today (section 26.10)** **REDESIGNED 2026-11-03 (29.9, D96 to D103): one node `find_differences` (audit + scan + judge + merge) replaces `check_one` and `find_missing`; `find_bugs` stays separate; 4 lessons (`find_bugs` is not typed yet).** **D106 (2026-11-10, 29.15): `find_bugs` reads only B; A alone is explained with the `REFERENCE` instruction and never hunted (built; its answer is measured with M31).** **M31 (2026-11-09, 29.12): at the end of the slice, measure the prompt id in each finding line (`see B-12`).** **DONE 2026-11-10 (29.17 to 29.20): D104 built (saved findings, whole last answer, the reply says what was reused; follow-ups 7 calls instead of 27), D106 checked on four real files, M31 measured and NOT kept (no gain), the rewrite reads the whole answer, closing review with 16 breaks caught. Next: slice 10.** **Then D104 (moved here 2026-11-09, 29.10): follow-ups get the whole last answer and the findings and claims saved once for each pair of files, with its test M33.** | medium, 4 lessons |
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

### 5. THE OUTLINE GAP — the planner cannot use the outline we have

The user asked whether the planner can see an outline of A and B, given that
artifacts arrive whenever the user chooses. Reading the code says: **not with
today's function.**

`build_context` builds its outline **from the chunks already in hand**. On the
search path that is the ~20 retrieved ones, plus a `totals` sentence saying
*"20 of 8333 parts were retrieved"*. It never knew the other 8,313.

**The planner runs BEFORE retrieval and has zero chunks.** So it needs a
different thing: a **corpus map**, read from the database without pulling text.

```
select source, count(*), min(start_line), max(end_line)
from chunks where artifact_id = $1
group by source order by min(chunk_index)
```

A few dozen rows for an 8,333-chunk repository, no `text`, no vector — the same
shape as `measure()`: ask the database a question, move no rows.

**And the two documents answer different questions**, so the template is not
reusable as it stands:

| | today's outline | the planner's map |
|---|---|---|
| runs | AFTER retrieval | BEFORE retrieval |
| answers | *"what did you NOT get?"* | *"what is in here?"* |
| purpose | stop a false *"the code does not do X"* | decide what to search for |

Reuse the **ladder**, `_by_file`'s consecutive grouping, and `defines:`. Drop
the included/not-included column (meaningless before retrieval) and the id
spans (prompt ids do not exist yet).

**And it inherits the same scaling problem**: `defines:` costs **44.9 tokens
per file** and compresses only **1.5x** (410 chunks to 270 labels), so a
500-file repository is ~22,000 tokens — nearly the whole prompt budget.

### 5b. THE MAP — ranked and elided, and D3 was revised

*Added later the same session. The first version of section 5 described the map
as a flat per-file list and gave it `OUTLINE_BUDGET`. The user rejected both:*

> *"only lines + defines... maybe of them has same defines... i think worth to
> increase it cuz its one call and worth be detailed."*

*He was right that the rows are too thin, and the research says he was wrong
about the fix. Both halves are recorded.*

#### What people actually build — aider's repo map is the reference

Three stages: **parse, rank, fit.**

```
1  tree-sitter parses every file, extracting definitions and references
   (130+ languages)
2  build a GRAPH - file A references a symbol defined in file B
3  PageRank over it, so heavily-referenced code floats up. The current chat
   biases the restart vector, 50x
4  render the top symbols as SIGNATURES with bodies collapsed to a marker
5  binary-search the ranked list for the largest slice that fits the budget
```

And the rendering is far richer than a name list:

```
aider/coders/base_coder.py:
...
 class Coder:
     abs_fnames = None
...
     @classmethod
     def create(
         self,
         main_model,
         edit_format,
         io,
...
     def abs_root_path(self, path):
...
```

#### THE NUMBER THAT ARGUES AGAINST A BIG BUDGET

> **⚠ CORRECTED 2026-09-28 — this heading OVERSTATES aider.** Its own docs,
> re-read: the 1k is a **default**, the repo-map page gives **no measurement**
> that a smaller map is better, and aider **expands the map "significantly"
> when no files have been added to the chat** - `--map-multiplier-no-files`,
> default **2**. Our planner is ALWAYS in that no-files case, because the map is
> the only view of the repository it gets. So aider's own behaviour argues for
> MORE room here, not less. See
> [section 12](12-planner-map.md#12-the-planner-map-is-built-and-its-budget-was-corrected--2026-09-28).

> **aider's repo map defaults to `--map-tokens 1000`.**

One thousand, for a whole codebase, in a top-tier coding agent. It can afford
that because it **ranks** and sends only the best rows.

And the reason is measured. Context rot, 2026, across 18 frontier models:

```
accuracy falls 30-50%   well before the documented limit
lost-in-the-middle      20 documents (~4,000 tokens) took accuracy from
                        70-75% down to 55-60%
past 200K tokens        30-60 point losses on multi-fact retrieval, on
                        models advertising a 1M window
same-topic junk         measured as ACTIVE DISTRACTORS, not inert filler
```

**A long flat file list is exactly same-topic junk** - hundreds of rows that
look alike, most of them irrelevant. It is the worst possible shape for
attention, and it is what the first version of section 5 proposed.

> **The axis was wrong on both sides.** The fix for a thin map is not MORE
> tokens and not FEWER. It is **richer rows, ordered by importance**.

#### What we can build with no new dependency

We already store more than section 5 used. A chunk header is:

```
[B_train.py · class Trainer · def fit · part 1/5 · lines 1189-1215]
```

That is a **signature-level label per chunk**, produced by our own AST
splitter. So an aider-shaped map is mostly available already:

```
B_train.py   78 parts, lines 1-1420
  class QuoraTokenizer   lines 425-520    __init__, encode, _build_stop_mask
  class Trainer          lines 920-1317   fit, _backprop_with_scaler, evaluate
  (module level)         lines 1-120      config, imports
```

Class and method nesting kept, line numbers kept. Measured cost on this
repository: **410 chunks compress to 270 distinct labels**, roughly **2,700
tokens for 94 files** - far richer than `defines:` and about the same price.

**Ranking is the part we do not have.** Aider ranks with a symbol graph; we
store no cross-file references. But we own something aider does not: **the
user's question and an embedder.** Ranking files by cosine against the question
costs **zero extra calls**, because the question is embedded for search anyway.

#### D10 to D13

| # | decision |
|---|---|
| **D10** | The planner gets its **own budget**, `PLANNER_BUDGET`, not `OUTLINE_BUDGET` - the two compete with different things. Applied **per tier** as `min(PLANNER_BUDGET, what this tier can take)`, which is section 11.1's grid. **35 of 40 tiers hold 250,000+**; the line that matters is **16,000, Gemma's input cap**, which is the largest free quota in the project. **SET TO 12,000 on 2026-09-28** - what is left of that cap after the 10% margin and the rest of the call, not half of it. Slice 4 makes it DYNAMIC per call. See [section 12](12-planner-map.md#12-the-planner-map-is-built-and-its-budget-was-corrected--2026-09-28) |
| **D11** | The map is **RANKED and ELIDED**, aider-style, built from headers we already store. **Rank only when it does not fit** - most repositories fit, and then ranking is a cost with no benefit. **Cosine first (free), a reranker as a measured upgrade.** And **BIAS, never filter**: every file keeps at least one row, because hiding what the question does not mention is the one failure the map exists to prevent |
| **D12** | Check the **Jev family and any new decision-model providers** in the catalogue, with M3. Jev is listwise, typed and ~1.2s, so it is a natural ranker for map rows as well as for chunks |
| **D13** | **D3 IS REVISED, at the user's instruction: use FUNCTION CALLING where the tier supports it, and STRUCTURED OUTPUT where it does not.** The honest cost is **two code paths** in the LLM layer instead of one, and a per-tier capability flag that has to stay true. The honest gain is provider-enforced arguments on the tiers that have them. **M3 decides how many tiers that actually is** - if it is most of them the hybrid is worth it, and if it is few, D3 stands as written. **M3 RESULT: 23 of the 24 tiers that answered, so D13 stands (section 9).** *Scope, written 2026-10-08 as D29: which nodes use it and which do not — [19.3](19-design-decisions.md#193-where-function-calling-is-used-d13-scope--d29).* |

**The knob is a knob.** `PLANNER_BUDGET` is a CEILING until **M5** sweeps it,
and the sweep must include a **1,000-token control** and a **DYNAMIC** budget.
*(Rewritten 2026-09-28: this used to call aider's 1k "the strongest argument on
the other side". It is a default, not a measurement - see the correction
above.)*

Sources: aider's repo-map post and docs (aider.chat) · Repository Map Pattern
(agentpatterns.ai) · Context Rot (tinyfish.ai, redis.io).

### 6. MEASUREMENTS OWED

| # | measure | slice |
|---|---|---|
| M1 | ~~does LangGraph fit 512MB~~ **MEASURED 2026-09-23 — yes, ~55MB imported and the whole container is 74 MiB under load. See [section 10](10-slice-0-memory.md#10-slice-0-is-closed-and-the-memory-budget-was-6x-wrong--2026-09-23)** | done |
| M2 | ~~latency ranking of all tiers~~ **MEASURED 2026-09-29 — 50 tiers ranked at a ~500-token answer. Report length is NOT measured. See [section 15](15-slice-1-latency.md#15-slice-1-is-measured--every-tier-ranked-by-speed-2026-09-30)** | done |
| M3 | ~~which tiers support function calling~~ **MEASURED 2026-09-23 — 23 of the 24 tiers that answered. See [section 9](09-function-calling.md#9-m3-is-measured--function-calling-2026-09-23)** | done |
| M4 | the raw question **vs** planner-written queries **vs** claims, scored against `EXPECTED.md`. Decides whether claims earn their cost (D39) | 13 |
| M5 | the planner **with** the corpus map vs **without** — a planner with no map is guessing, which is what HyDE does. **AND THE BUDGET SWEEP** (added 2026-09-28): fixed **1k · 4k · 8k · 12k** against a **DYNAMIC** budget (the tier's input limit / 1.1, minus what the rest of the prompt really costs). Score the queries on how many known divergence locations in `EXPECTED.md` / `queries.json` they reach, not on how they read. Record planner latency beside it, and which tier answered. **A THIRD ARM (added 2026-10-18, D47):** the map PLUS the stored summaries of A and B, against the map alone. Count any wait for a summary as planner latency. Measure a small artifact (summary read whole) and a big one (summary cut) as two separate cases **AND THE QUERY CAP** (added 2026-10-18): `MAX_QUERIES` in `agent/plan_check.py` (12 until 2026-10-20, 6 now) is a first guess that only stops a runaway list, not a measurement. Record how many queries the planner writes for each question, and set the cap above the largest good plan and below a runaway, with the cost of one search (embed, search, rerank) and the quota beside it. **ANOTHER ARM (added 2026-10-22, D63):** the planner returns a cleaned question beside its queries (asked FIRST in its answer), used for the search only. Score the queries as above, and add about 10 GOOD questions that must come back unchanged (count the unchanged rate, and read by hand any change of meaning). M4 gets the same arm. | 13 (was 4) |
| M9 | **A's FULL TEXT in the planner call** (question + map + the paper) against question + map alone. When A is small this merges the planner and `extract_claims` into ONE call. Added 2026-09-28. **ANSWERED yes by the user on 2026-10-14 (D40); the time it saves is measured in slice 7** | 7 |
| M6 | **a findings score on the SEARCH path** — never once measured, see C3. This is the baseline Step 2 must beat | 13 |
| M7 | an exact-match tool vs vector alone (D8) | 13 |
| M8 | **per-node output tokens and latency** — every time estimate in this section rests on an assumed 40s per node | 13 |
| M15 | **`verify`: an LLM with function calling against Jev** (added 2026-10-18, the user's call, D48). The same claims and the same evidence chunks go to both. Score the verdicts (match / mismatch / absent) against the known answers, and record the speed of the checks, the cost and how often each one fails. Run the LLM arm on at least two tiers, because the chain falls back. Run the Jev arm twice: all claims in one call, and one claim per call, because Jev's answer depends on the other questions in the same call. Jev gives only the verdict; the quote comes from the best chunk found by code. Name the corpus beside every number: `quora_siamese` is the only pair with known verdicts. **Since 2026-10-23 this is the PILOT of D73: it runs at the end of slice 7, and its result decides whether slice 14 goes on as planned** **MEASURED 2026-10-24, section 25.5.** | 7 |
| M16 | **the planner's list of steps: one LLM call against Jev** (added 2026-10-18, the user's call, D48). Arm A: ONE LLM call returns the steps and the queries (function calling). Arm B: Jev answers one yes/no question per allowed step, then an LLM writes the queries, one after the other. Arm C: the same as B, but the two calls run at the same time (both need only the question and the map). Score the steps against about 30 questions, each with the correct plan (the set planned in 19.5, point 5), with the LLM on at least two tiers. Score the queries as M5 does (how many known divergence locations they reach). Record the planner's time and cost. The user's worry is that the LLM steps may be fast but less exact; arm C tests the other worry, that Jev is slower The same questions test the allowed steps for each file count (`STEPS_BY_FILES` in `agent/plan_check.py`, a first proposal): count how often a correct plan needs a step that the list does not allow. **Moved to slice 14 on 2026-10-23 (D73).** | 14 (was 13, was 4) |
| M17 | **fix quality** (added 2026-10-18, D49). For the known findings of `quora_siamese` (and of the new pair from slice 12), is the fix that the report proposes right? Score each proposed fix as right, partly right, wrong or not given, and count the fixes that would break the code. Run it for the one-artifact report and for the two-artifact report, on at least two tiers. Compare `respond` writing the fix in the same call against a separate `propose_fix` call after the findings, and record the extra time and the extra calls. `EXPECTED.md` needs a "right fix" column first. As with every answer key, it may be used to score the fixes and never to write the prompt | 13 |
| M18 | **the instructions and prompts of slice 6, on more data** (added 2026-10-22). Everything measured in slice 6 is a SMALL sample: one pair, at most 8 tiers, one run per cell, regex screens, 5 calls lost to Google 503. Re-measure `CHAT`, `ONE_FILE` and `TWO_FILES` (and `REPORT` as the baseline) on the new pair of slice 12 and on `quora_siamese`, on at least 6 tiers including cheap ones, with several worded versions of each question (at temperature 0 a repeat gives the same text), on the SEARCH path and not only on a pair that is almost whole. Score findings against an answer key with the impact column, never by regex alone, and score the "do the causes add up" verdict separately. Also test: the last answer inside the two-file prompt for follow-ups that need its exact words; the section order and the length limit; one call for the answer and a second for the arithmetic, or the verdict from Jev (M15 style); and whether a better approach than one long instruction exists. This may change the instructions, the prompts or the approach. D60 is a first choice, not a decision | 13 |
| M24 | **rerank for each claim, or not** (added 2026-10-23, the user's call). Lesson 2 of slice 7 sends the first 6 parts of the plain fused search for each claim, with NO rerank. At the end of slice 7 (after lesson 3, with M10, M11 and M21) run one small test on `quora_siamese`: for each known claim, how often is the right part of B inside the 6 that are sent, without a rerank and with a Flash-Lite rerank of the fused list; and note what the retry loop of lesson 3 fixes alone. It needs only search and rerank, about 20 requests, and no check calls. Add the rerank (one injected function, `rank_pile(claim.text, pile)`) only if the number goes up clearly. Cost to weigh: about 31 Flash-Lite requests for a question against about 16 **MEASURED 2026-10-24, section 25.4: no rerank.** | 7 |
| M25 | **Jev on the jobs of slice 14** (added 2026-10-23, D73). For each job one schema, then the LLM version against the Jev version on questions with known answers (the gate, `find_missing`, the labels, the follow-up check; the planner's steps are M16). The same rules as M15: two LLM tiers, Jev with one question for each call and with all of them in one call, and the speed, the cost and the failure rate beside every score, with the corpus named beside every number | 14 |

**The cache pays for most of this.** `.cache/` holds 2.4GB: 26 corpora already
embedded, 50 rerank result files, 18 top-N runs. M4 and M7 can reuse it instead
of spending quota.

### 7. CODE OWED

| # | change | where |
|---|---|---|
| CC1 | ~~`outline_of(conn, artifact_id)`~~ **DONE 2026-09-28 as `read_headers` + `file_scores`** — headers only, no text, no vectors | `store/reader.py`, `store/search.py` |
| CC2 | ~~a SECOND renderer for that map~~ **DONE 2026-09-28 as `build_map`** | `prompts/corpus_map.py` |
| CC3 | the `agent/` package — core layer, injected callables | `labpilot/agent/` |
| CC4 | a JSON helper: ask with a schema, parse, retry. Extend `generation_config` past reranking | `llm/` |
| CC5 | wiring — build the graph, inject the callables, map the new errors | `api/` |
| CC6 | `requirements.txt` and `test_packaging.py`, if LangGraph is added | root |
| CC7 | ~~a budget ladder for the map, for the 500-file case~~ **DONE 2026-09-28** — level 3 counts files by folder | `prompts/` |
| CC8 | **the DYNAMIC planner budget** — `min(PLANNER_BUDGET, tier input limit / 1.1 − cost of instructions + question + schema)`, computed per call. Cannot be written before the planner instructions exist | slice 4 |


### 11. NOT STEP 2

MCP and web search are **Step 2.5**. The UI, SSE progress and the TypeScript
rewrite are **Step 3** — and note that *"Searching the web..."* in a chat
product is nothing but the app rendering the plan steps as they run, so the
planner's JSON gives us those labels for free. Fine-tuning is **Step 4**.
