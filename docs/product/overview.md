# Product overview

[Docs home](../README.md)

## Project Overview

LabPilot is an agent-based tool that compares two pieces of work — a research
paper vs. code, or code vs. code — and explains **why their results diverge**,
then proposes the next experiment to test.

It is a portfolio capstone project, deliberately scoped to close four specific
skill gaps: **RAG**, **vector databases**, **agent orchestration** (including
MCP), and **LLM fine-tuning**.

### Comparison modes
- **Paper vs. Code** — a paper's claims/methodology against an implementation
- **Code vs. Code** — two implementations against each other
- The "Code" side accepts either a single file/notebook or a full repository —
  same comparison logic either way, just more files to retrieve from.

### What every comparison must surface
1. Bugs or implementation errors
2. Differing approaches / design choices between the two sides
3. Missing details (hyperparameters, preprocessing steps, seeds, library
   versions) that the code had to assume
4. A causal explanation for *why* the results likely diverge — not just
   "these differ"
5. A concrete suggestion for the next experiment to run

### Input shape — artifacts are state, the prompt is per-turn

*(Clarified 2026-08-11.)* The two arrive on different schedules, and that
asymmetry drives the whole design:

| | Artifacts | Prompt |
|---|---|---|
| When | **Whenever the user adds one** | **Every turn** |
| Required | Not up front — see preconditions below | Optional on turn 1 (a default is supplied), required after |
| Cost | Expensive — chunk + embed everything | Cheap — one small embed |

The artifacts are **state** living in pgvector, not input. After an artifact is
ingested the only thing crossing the wire each turn is a prompt.

**The prompt does two jobs, and the second is the one people miss:**
1. It steers what the answer covers.
2. **It *is* the retrieval query** — the thing that gets embedded and matched
   against stored chunks. No prompt, no query vector.

So the UI shows a **prefilled, editable** chat box — never a grey placeholder.
The user must see what will be asked, because it also decides what gets
retrieved. Three rules follow:
- **Never send empty.** A cleared box falls back to the default, or retrieval has
  nothing to search with.
- **Version the default prompt.** It is a retrieval query, so re-wording it
  changes which chunks return. Log which version produced each report or reports
  stop being comparable.
- After turn 1 the box empties — the artifacts are already ingested.

**This is why the embedder is a migration and not a fallback.** Ingest embedded
the artifacts with one model, so every later prompt must use that *same* model
forever. The two schedules create the lock-in.

### Artifact count — flexible input, focused identity

*(Decided 2026-08-11.)* Artifacts are **not** a fixed pair collected up front.
They accumulate in the session, and each capability declares how many it needs:

| Artifacts in session | What becomes possible |
|---|---|
| **0** | answer coding questions from the prompt alone |
| **1** | `summarize`, `find_bugs`, explain this repo |
| **2** | **+ `align`, `verify`, `explain_divergence`** — the flagship |

So the planner filters capabilities by what the session actually holds. A user
can chat for three turns, add a repo at turn 4, add the paper at turn 6, and
`compare` simply becomes reachable. **The change this needs is one precondition
field per capability — nothing else.**

**But the product identity does not become "a chatbot that reads files."** That
was considered and rejected, for three reasons:

1. **The pitch.** *"Explains why your reimplementation gives different numbers"*
   is specific and memorable. "Chat about your code" is every other AI tool.
2. **The forcing function.** The alignment map, the correspondence gate and the
   verify loop exist *only because* two artifacts must be reconciled. Remove the
   constraint and the three things this project exists to teach disappear with it.
3. **Focus beats generality on the specific task.** Retrieval strategy, prompts
   and output template are all tuned for divergence analysis.

Also practical: the fine-tune dataset is ~150–300 divergence explanations. If the
app does anything, there is nothing coherent to fine-tune on.

**So: 0- and 1-artifact modes are supporting features that come free once the
capability library exists. Two artifacts stay the headline.**

**Cap at 2 for now.** A third slot (the paper's official implementation, found by
[web search](../agent/design.md#web-search--step-25-opt-in-and-where-mcp-finally-fits)) is a
Step 2.5 addition and does not change the layout.

**Build order is unchanged.** Step 0 slice 4 still hardcodes exactly two
artifacts and one prompt. That is the *hardest* path, so building it first proves
the architecture; "chat about code" would work on day one and teach nothing.
Preconditions arrive with LangGraph at Step 2, where they are nearly free.

### Edge cases to handle explicitly
- **Mismatched domains** (e.g. a psychology paper + an ML repo): detect and
  report "no meaningful correspondence found" — never hallucinate a comparison.
  **This needs its own gate step, not an instruction inside the main prompt** —
  see [The correspondence gate](../agent/design.md#the-correspondence-gate--step-2) (redesigned 2026-10-29, D78: [section 28](../step2/28-slice-8-gate.md#28-slice-8--the-correspondence-gate-redesigned-on-summaries--decided-2026-10-29)).
- **Notebook vs. large repo**: rely on the RAG retrieval layer to narrow the
  repo down to relevant files. Never dump a whole repo into context.
- **Cross-language comparisons** (e.g. Python vs. C++): a **legitimate**
  comparison, not a mismatch — but the gate can falsely reject it, because
  embeddings score surface similarity and the same algorithm looks different in
  two languages. Fix: summarise each code unit to natural language **first**,
  then embed the summary. That collapses `for i in range(n)` and
  `for(int i=0;i<n;i++)` to the same description. Route the alignment reasoning
  to the **top** of the generator chain, never to a weak tier, and never to the
  fine-tuned model — that is a demo artifact, never on the live reasoning path.
- **Partial correspondence** — a repo implementing only half a paper. This is the
  common real case and the one most designs forget. Correspondence is a
  **spectrum, not a boolean**.

