# Layout and the four layers

[Docs home](../README.md)

### Layout — plan the shape early, create files late
Reorganising a project is cheap on day one and expensive in month three, because
by then imports, tests, and habits all point at the old shape. So the **map** is
decided up front. But there is a line, and it matters:

> **Planning where a file will live costs nothing. Writing an abstraction before
> its second case costs a rewrite.** Decide the folders early. Create each module
> the day it has real content — never as an empty placeholder.

**"Wait for the second case" is not one rule — it depends on the cost of being
wrong.** Split it in two:

| Kind of thing | When to give it its own module |
|---|---|
| **Constants and pure helpers** (timeouts, budgets, a `truncate` function) | As soon as a second consumer is **known and scheduled** — not after it is written. Moving a constant later is a rename the tests catch in seconds. |
| **Abstractions** (base classes, `Protocol`s, plugin interfaces) | Only after the second implementation **exists** and its real differences are visible. Guessing the shape costs a rewrite. |

So a `defaults.py` may be created for the provider that is next in the plan.
A `base.py` may not be created until that provider is actually written.

**Design against the roadmap, not against today.** When proposing structure,
assume the next two steps in the build plan already exist and ask where each
piece would sit then. Structure that is correct only for the current file is
not correct.

**How to split — one module, one reason to change.** Not by line count.
Ask: *"when X changes, how many files do I touch?"* If one change edits five
files, the split is wrong. If five unrelated changes all edit one file, it is a
god-file.

Line count is only a **symptom to investigate**, never the rule:

| Signal | What it usually means |
|---|---|
| Module past ~400 lines | Probably holds more than one responsibility — look for the seam |
| Module under ~30 lines | Probably belongs inside its neighbour |
| Two modules always edited together | They are one module |
| A module imported by everything | It holds contracts — good, keep it dependency-free |

**Contracts live alone.** Value objects and exception types (`LLMResult`,
`Attempt`, `LLMError`) go in their own modules that import nothing from the
package. Every layer imports them; they import no one. This is what prevents
circular imports — the failure that forces a real reorganisation.

### The four layers — measured 2026-08-27, enforced by a test

*The user asked whether the growing folder list should be reorganised — into
`rag/`, or into `shared/ adapters/ core/`. The question was answered by reading
the real import graph rather than by opinion.*

```
tokens, _text   imported by everyone, import nothing
embed           -> tokens, _text
llm             -> tokens, _text
ingest          -> tokens
prompts         -> ingest
retrieval       -> ingest
api             -> everything
```

**No cycles. The layers were already there** — nobody had written them down.

| layer | meaning | packages |
|---|---|---|
| **shared** | imported by all, imports nothing of ours | `tokens`, `_text` |
| **adapters** | talk to the **outside world** — HTTP, disk, git, a database | `llm`, `embed`, `sources`, `store`, later `rerank` |
| **core** | our own logic, no outside world | `ingest`, `prompts`, `retrieval`, later `agent` |
| **entry** | wires everything together | `api` |

The rule each layer obeys: **shared imports nothing · adapters import shared ·
core imports shared and core · entry imports anything · nothing imports entry.**

#### Why not a `rag/` folder, and why not nested layer folders — yet

A `rag/` folder would hold `ingest` + `embed` + `retrieval`. But `embed` is an
**adapter** (HTTP to Mistral) and `ingest` is **pure logic** — same topic,
different kind. And `llm`, which shares every pattern with `embed`, would land
in a different group.

> **Group by what depends on what, not by what sounds related.** A folder's job
> is to make a wrong import obvious; a topic folder cuts across the arrows and
> hides one instead.

**Nested layer folders (`shared/ adapters/ core/`) are the right shape and are
still not built**, because they buy nothing a test does not already buy, and
they cost a move of every file mid-project. **Revisit at Step 2**, when `agent/`
lands and core reaches five packages — by then the test has kept the layers
honest, so the move is mechanical rather than archaeological.

#### The rule that actually matters

> **A folder is a suggestion. A test is a rule.**

Nothing stops `llm/` importing `api/` tomorrow. The folders would still look
tidy and the design would be broken. So the layering is pinned by
`tests/unit/test_architecture.py`, which parses every import in `labpilot/` and
fails on a crossed line. It sits at the top of `unit/` beside
`test_packaging.py`, because it crosses every package.

**Every package must be assigned to a layer**, and an unassigned one fails the
suite. That is the same *pin the exceptions by name* pattern as
`OUTPUT_TOO_SMALL`: a new package cannot be added without someone deciding what
it is.

**Mutation testing deleted one of the four tests I wrote.** All four mutations
were caught — an unclassified package, an adapter importing the API, a
misclassified `api`, and a cycle inside core — but reading *which* test fired
showed that `test_nothing_imports_the_entry_layer` **can never fail alone**:
any importer able to reach `api` is already refused by the layer rule. It was
deleted rather than kept as a comforting green line.

> **"A mutation was caught" is not the check. "Which test caught it" is.** A
> passing mutation run hid a dead test until the names were read — the same
> mistake as counting walk lines instead of reading them.

**Each package's `__init__.py` is its public API.** Re-export the names the rest
of LabPilot may use. Outside code imports `from labpilot.llm import LLMClient`,
never `from labpilot.llm.openai_compatible import ...`. Internal files can then
be renamed or split freely without breaking a single caller. The `LLMClient`
seam rule is enforced by this, not by good intentions.

**Tests mirror the source tree, and are split by kind — not all in one folder:**

```
tests/
    conftest.py           shared fixtures and the --run-smoke flag
    unit/                 one module at a time; mirrors labpilot/ structure
    integration/          several real layers, mocked only at the outer edge
    api/                  FastAPI TestClient against the endpoints
    smoke/                anything that spends API quota; opt-in only
```

Folders are created when their first real test exists, not before.

**The split is by *cost*, not by scope.** *(Clarified 2026-08-14.)* This is not
the textbook meaning — in the usual sense, a test that runs the chunker, the
selector and `LLMClient` together is an *integration* test. Here it lives in
`smoke/` for one reason: **it spends a request from a 50/day pool, so it must
never run by default.** Ask *"what does this test cost, and what must be
switched on for it to pass?"*, not *"how many layers does it touch?"*

Two consequences:

- **`unit/` may read a committed sample file.** The old wording said "no I/O",
  which `test_chunker.py` broke on day one. Reading a fixture that lives in the
  repo is neither slow nor an outside service. **No network and no database** is
  the real rule, and all 126 unit tests still run in under half a second.
- **A test that crosses packages sits at the top of `unit/`**, not inside a
  package folder — `tests/unit/test_pipeline.py`. The "mirrors `labpilot/`"
  rule applies to tests of one module; a test of the *seam between* modules
  mirrors nothing.

**Never name a test after a slice number.** `test_slice3_chain.py` was written
and renamed the same day. Slice numbers are temporary scaffolding and the file
outlives them; in a month "slice 3" means nothing while "the pipeline answers"
still does. Name a test by **what it checks**.
