# Section 19: design decisions of 2026-10-08

[Docs home](../README.md)

### 19. Design decisions of 2026-10-08 — made while teaching slice 2, lesson 2

*Talked through with the user in plain words during lesson 2. Most of it started as the
user asking what we really do about something. **Nothing here is built.** Where a point is
Claude's reading and not the user's decision, it says so.*

| # | decision | where |
|---|---|---|
| D1 | clarified: plan-and-execute is the main shape, with exactly one bounded ReAct loop | 19.1 |
| D29 | function calling is used for nodes whose output code reads, and not for prose nodes | 19.3 |
| D30 | the planner is a model call; keyword rules are dropped as the chooser | 19.5 |
| D31 | one final node, `respond`, ends every plan | 19.7 |
| D32 | the UI has two controls, Effort and Strength | 19.8 |
| D33 | two kinds of web search; the one written in this file is the heavy kind | 19.9 |
| D34 | function calling gets its own small lesson before slice 4 | 17.10 |

#### 19.1 Plan-and-execute and ReAct together (D1 clarified)

The user remembered a mixture, and the user was right. The old D1 heading said "not
ReAct", which hid the other half.

- **Main shape: plan-and-execute.** The planner writes the plan once. The graph runs it.
- **ReAct in exactly ONE place (D4):** `verify` says "not found", the program searches
  again with a better query, at most 2 more times.

```
claim: "gradients are clipped at norm 1.0"
try 1  query "gradient clipping norm"   -> chunks without the clip line -> verify: absent
try 2  the model writes a better query: "clip_grad_norm_ CLIP_NORM"
       -> finds CLIP_NORM = 1.5          -> verify: mismatch -> stop
```

After 2 retries with `absent`, the final verdict is "not found in the chunks I
retrieved", never "the code does not do it". In the graph this is a cycle
(`search -> verify -> search`) with a counter `tries` in the state. A loop with no limit
can run forever, so the counter is the hard stop.

*Claude's suggestion, NOT decided (decide in slice 7):* code decides to loop (verdict is
`absent` and `tries < 2`), and the model only writes the new query.

**What the big products do** (from the session of 2026-09-22/23, "Session context recall";
read from their behaviour and public writing, not from their source): normal chat uses
ReAct; Deep Research plans first and shows a written plan; coding agents use a plan and
then ReAct inside each step. F9 says plan-and-execute is better for long tasks with
parallel steps, and it is weak evidence (one benchmark).

**A ReAct agent is also a graph in LangGraph:** two nodes (`model`, `tools`) and a loop.
The state is a growing list of messages, so it uses a reducer. LangGraph runs both
designs. The difference is who chooses the next step: the model at every step (ReAct), or
the plan, written once (ours).

**OPEN:** how much ReAct. This file fixes ONE loop. D8 (an exact-match search tool) is a
candidate that could give the loop a second tool. "A plan, then ReAct inside each step"
like coding agents would be a NEW decision.

#### 19.2 The words: node, capability, tool, function calling

| word | meaning here |
|---|---|
| **node** | one step of the graph, written as one Python function. `search`, `extract_claims` and `verify` are nodes |
| **capability** | this file's name for a node's job, with its rule about how many artifacts it needs |
| **tool** | a function the model may ASK our code to run |
| **function calling** | the model's answer is a function NAME plus ARGUMENTS, as JSON |

**The direction is the point (the user read it the other way for a long time).** We send a
normal prompt, plus a DESCRIPTION of a function (its name, its arguments, the allowed
values; a JSON schema, the same idea as a Pydantic model). The model WRITES the name and
the arguments in its answer. The model never runs anything. It only produces text. Our code
reads the answer.

```
we send:      messages (the normal input)  +  tools: make_plan(nodes: list of
              "summarize" | "find_bugs" | "answer_question")
model writes: make_plan({"nodes": ["find_bugs"]})
our code:     json.loads(arguments)["nodes"]   -> ["find_bugs"]
```

- **Case 1, a real tool.** A real Python function exists (`search(query)`). The model writes
  `search({"query": "..."})`, our code runs the real function and sends the result back.
- **Case 2, a shape only.** No real function exists (`make_plan` is just a name we invented).
  The arguments ARE the answer. Our code only reads them. The provider checks that the shape
  is valid, so we get clean JSON with allowed values only.

Both cases use the same format. **In LabPilot almost every use is case 2.** Case 1 can appear
only in the D4 loop and in D8.

#### 19.3 Where function calling is used (D13 scope = D29)

D13 says function calling first and structured JSON as the fallback. It never said which
model calls. **D29, the rule:**

> **If code (or a later node) reads parts of the output, use a shape (function calling
> first, JSON text as the fallback). If only a person reads it, use plain text.**

The first column is the agreed rule. The per-node answers are Claude's reading, and each one
is confirmed when that node is built.

| node | output | why |
|---|---|---|
| planner | **shape** | code reads the node names, the queries and `effort` |
| decontextualize (turn 2 rewrite) | plain text | one string, used as the search query |
| `answer_question`, `summarize` | plain text | a person reads it (a shape only if a later step reads fields) |
| `extract_claims` | **shape** | a list of claims, each with a source tag |
| ~~`extract_outcomes`~~ | withdrawn 2026-11-12 (D108, section 31) | no such node: the `result` claims and the answer instruction do this job |
| search / BM25 | no model | code only |
| rerank (listwise) | **shape** | a list of positions. This already exists in `api/reranking.py` |
| correspondence gate | **shape** | a verdict (FULL, PARTIAL, NONE) and a reason, read from the two summaries (D78, section 28). The 2026-10-08 row said "no model, computed from the similarity scores"; that is replaced |
| `verify` | **shape** | verdict (`match`, `mismatch`, `absent`) plus evidence |
| `find_bugs`, `find_missing`, `diff_choices`, `align`, `propose_fix` | **shape** | lists the next node reads |
| `explain_divergence`, `propose_next`, `write_code` | plain text | a person reads it (see 19.7: these are merged into `respond`) |

**Why not make every node a tool (case 1) when the plan is already decided.** There is
nothing left for the model to choose, so forcing it to "call" each node adds a request per
node and gives nothing. For one `verify`: request 1 the model writes `verify(claim 3)`,
request 2 `verify` itself asks the model to judge, request 3 the verdict goes back to the
model. Directly it is ONE request. It would also make the model choose the order every
time, which is ReAct, and steps could not run in parallel. It is **not** a technical limit:
23 of 24 tiers support function calling. A node is called by the graph, and the model is
called inside the node.

**OPEN detail for CC4 (the JSON helper).** M3 found two different tool failures.
A tier can accept `tools` and return nothing (Kilo's Nemotron 3 Super): "detect, never
configure" covers it, because the body is parsed as JSON. A tier can also REJECT `tools`
(GLM-5.2, both routes: 404 "No endpoints found that support tool use"): the request itself
fails. Not decided: retry the same tier without `tools` and with JSON asked in the prompt,
or skip the tier.

#### 19.4 The state may mix plain text and structured values

Each state key has its own type, so plain-text nodes and shape nodes sit in one state. The
shape only matters INSIDE a node: the node turns the model's answer into a normal Python
value and puts that in the state. The state never stores "a function calling answer".

```python
class State(TypedDict):
    question: str
    summary: str
    bugs: Annotated[list[Bug], operator.add]
    report: str
```

#### 19.5 The planner: a model call, not keyword rules (D30)

The user's decision: **a model call is cheap, so the planner is one model call (D2) and the
keyword-rule idea is thrown away as the chooser.** This settles the old "not fully joined"
note (the older note said not to spend a model call to decide how to spend model calls).

**The steps:**

1. Code counts the files. The count limits the allowed nodes (the precondition on each
   node): 0 files -> `answer_question` only; 1 file -> also `summarize`, `find_bugs`,
   `write_code`, `propose_next`; 2 files -> all.
2. One cheap call gets the question, the corpus map (`PLANNER_BUDGET`) and the allowed nodes.
3. It returns a plan as a shape (function calling, case 2).
4. The graph runs the plan.

| situation | plan |
|---|---|
| no files, "hi" or a hard question | `[respond]` (19.7) |
| 1 file, "what does this repo do?" | `summarize` |
| 1 file, "is there a bug in my loop?" | `find_bugs` |
| 1 file, "check my code" (vague) | `summarize`, then `find_bugs` (the default prompt for one file) |
| 2 files, "why do the results differ?" | `extract_claims -> verify -> ...` |
| turn 2 follow-up | `decontextualize`, then one of the plans above |

**Why a cheap model may be trusted: it is not trusted, it is fenced.**

1. A fixed shape: node names come from a fixed list, so it cannot invent a step.
2. A check in code: names exist, the file count allows them, the order makes sense.
   If not, the default plan runs.
3. A short, fixed, versioned instruction with two or three examples (long instructions made
   models worse in this project).
4. The plan is saved beside the report and shown to the user as steps, so a wrong plan is
   visible and the user can ask again.
5. A measurement in slice 4: about 30 questions with the correct plan for each, scored on
   at least two models (the chain falls back, so another model may plan).

**Backup:** the fixed default plan (every node, in order) runs when the planner fails.
*Optional, only if the measurement shows the need:* a check (not a chooser) that adds
`find_bugs` when the question says "bug" and the plan has none, or a rule "when unsure,
choose the bigger plan" (slower, misses less).

**Routing is done by code, not by the planner.** The planner names nodes. A table looks up
each node's chain:

```python
ROUTES = {"summarize": SUMMARY_CHAIN, "find_bugs": BUGS_CHAIN}
```

The planner does not know which model is free today. A decision that code can make should
not be left to a model. Decided: `summarize` leads with Gemma. **NOT decided:** the chain
for `find_bugs`. North Mini Code is a candidate, but this file lists it for `write_code`
and nobody measured it for `find_bugs`. Decide in slice 11.

#### 19.6 `summarize` runs in the two-file case even when nobody asked

Already designed (the correspondence gate section), recorded here because it was forgotten
once. In the two-file plan, `summarize` runs for A and for B BEFORE the gate:

1. If the gate finds no correspondence, the two summaries ARE the answer (a psychology
   paper and an image classifier), not an error.
2. They are sections 1 and 2 of the report.

Two calls on a cheap chain (Gemma). Order: `summarize` A and B -> gate -> `extract_claims`
-> and so on. **A different thing:** summarising each code unit in plain words before
embedding, so the same algorithm looks the same in Python and C++. That is an ingest-time
step, and only when the languages differ.

#### 19.7 One final node, `respond`, ends every plan (D31)

**The user's idea, agreed:** one node at the end of EVERY plan (0 files, 1 file, 2 files,
divergence), and not a different node for one task.

- **Code adds it** at the end of every plan. The planner does not list it, so a plan can
  never end without an answer.
- It takes over the writing-for-a-person job of `answer_question`, `explain_divergence`
  and `propose_next`. The name `respond` is Claude's proposal ("explain" sounds like the
  divergence report only). **The capability table in this file is NOT rewritten**; this
  section is the design intent until it is built.
- **0 files:** the plan is just `[respond]`.
- It reads the RESULTS in the state, not the raw chunks.
- The findings table is made by CODE and shown next to the text, so no detail is lost when
  the model rewrites a list. *(Claude's proposal; the user did not object.)*
- **Its instruction, chain, `max_tokens` and thinking level come from the plan and from the
  user's controls (19.8), not from the node.** For the divergence plan: the full report
  instruction and the strongest chain. Slice 8 job 9 measured that the report keeps the
  strong chain.

**The user first wanted "the best model every time". Corrected, and the reasons stay:**
the strongest models are slow (tier 1 took 119 to 497 seconds for a report) and scarce
(every Gemini Flash is 20 requests a day), and a simple message must stay cheap (the "no
ten minutes for a simple task" rule). Also a deep question can arrive with zero files, so
the file count cannot choose the chain.

**OPEN:** (1) the chain `respond` uses for plans between chat and divergence: one fixed
middle chain, or a chain chosen by the plan. Decide in slice 11, measure in slice 13.
(2) A plan that ends in a text-only node (`summarize` alone): call `respond` after it
(one more call) or not.

#### 19.8 Two controls in the UI: Effort and Strength (D32, Step 3)

```
Effort    Low | Medium | High        how much the model thinks and writes
Strength  Fast | Medium | Strong     which models can answer
```

Default Medium and Medium. The user changes each one alone. **This replaces the single
Fast/Balanced/Deep preset in the UI** (the thinking-level section keeps the reasoning).
Presets plus an advanced panel were considered and dropped: too many options at once.

- **Effort** = thinking level and `max_tokens`. **Strength** = which chain. These are the two
  knobs this file already kept apart (chain by task, thinking by preset). Claude mixed them
  up in this session and the user corrected it.
- **High effort** drops the tiers that cannot think deeply or cannot hold a long answer
  (Gemma 31B has no thinking knob; the Groq tiers and Devstral have small output caps).
- **Strength is a request, not a promise**, because the chain falls back. The page ALWAYS
  shows which model answered. The Strong chain should warn about quota (about 20 full
  reports a day).
- **The user's choice overrides the planner's guess.** That is why the controls exist.
  "Deep and hello" still gets High effort.
- The planner also returns an `effort` guess. It means thinking and length, NOT model
  strength, and it should use the same three words as the UI. If unsure: Medium. It is
  measured in slice 4 together with the plan.
- Do not map High to the provider's HIGH setting without a measurement: on the same prompt
  HIGH spent 93% of the budget on thinking and MEDIUM wrote 2.5 times more report.

#### 19.9 Web search: two kinds (D33)

**Correction.** The web search written in this file ("Web search — Step 2.5") is the
**HEAVY** kind: search -> fetch the pages -> chunk -> embed -> store -> rerank. Its job is
narrow (the official implementation, an arXiv paper, a library version, follow-up work),
but its mechanism is the full pipeline. Claude first called it "the fast, targeted kind",
and that was wrong. A plain web search is not written anywhere.

| | simple web search | the one written here (deep) |
|---|---|---|
| steps | one call to a search API (Bing, Brave, Tavily, DuckDuckGo) | search, fetch, chunk, embed, store, rerank |
| what the model gets | titles and snippets | ranked chunks from the pages |
| speed | fast | slower |

- A simple mode is a **possible addition**. A deeper mode would repeat the `web_search`
  node under a visible plan, like the products' Deep Research. Neither is built or decided
  in detail.
- **UI (Step 3):** a menu next to the question box with two choices, both OFF by default
  (web search stays opt-in), chosen per message. Not a settings panel. A command such as
  `@deepsearch` can come later.
- **What products do** (a snapshot; menus change and the sources disagree). ChatGPT: Deep
  research from the + tools menu, or by typing `@Deepresearch`; plain web search is a small
  removable tag in the box
  ([OpenAI help](https://help.openai.com/en/articles/10500283-deep-research-fa)). Claude:
  + menu -> Web search; Research is its own button and needs web search on; the newest
  Claude has no web search toggle and searches when it helps
  ([web search](https://support.claude.com/en/articles/10684626-enable-and-use-web-search),
  [research](https://support.claude.com/en/articles/11088861-use-research-on-claude.md)).
- The five safety rules are unchanged (query only from the paper's public identity,
  opt-in, found repos pass the gate, three-way labels, pages are data). Backend: Step 2.5.
  UI: Step 3.
