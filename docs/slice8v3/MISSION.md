# SLICE 8 v3 — THE MISSION. Read this file and start working.

**A fresh session needs nothing but this file.** It says why the run exists,
what to build, what to measure, in what order, and what must NOT be repeated.
Do not ask what to do — it is written here.

**Decided by the user on 2026-09-17, at the end of the v2 session.**

---

## 0. THE ONE SENTENCE

> **LabPilot is a Python and machine-learning tool that also supports other
> languages. The measurements do not reflect that, so they are being re-run on
> a corpus zoo where PYTHON DOMINATES — 10 of 20 — instead of 3 of 13.**

> **AND THE RUN ENDS BY RE-TAKING EVERY DECISION on the 20-corpus evidence —
> see Step 4. Measuring is not the deliverable; the decision table is.**

**Three rules that shape the whole run:**

1. **Run the 7 NEW corpora only.** The aggregates glob `.logs/results/`, which
   already holds the 13, so every table becomes a 20-corpus table with nothing
   old re-run — §2.5.
2. **Any subset must be at least HALF PYTHON**, because the zoo is — §2.6.
3. **Finish with `docs/slice8v3/DECISIONS.md`**, every decision restated, each
   row carrying its Python share — Step 4.

---

## 0.5 SET THE SESSION UP — this exact incantation, before anything else

Nothing works without all four parts.

```bash
cd "C:/Users/98922/Documents/python_scripts/AI/apps/labpilot"
set -a; source .env; set +a      # API keys
source .corpora/env.sh           # WHERE each corpus lives (gitignored)
# and every command needs BOTH of these:
PYTHONPATH=. .venv/Scripts/python.exe ...
```

**`python` is NOT the right interpreter.** It resolves to a 3.10 without our
dependencies. Always `.venv/Scripts/python.exe`.

### Before ANY call to a model, probe the exit

The user works through a VPN and Google refuses some exits. A refused exit
looks exactly like a dead provider in the logs — a whole session was once spent
writing "Google is blocked" into CLAUDE.md when Google was fine.

Step 1, which exit are we on:

```bash
curl -s https://ipinfo.io/json
```

Step 2, the verdict. It must be a real `generateContent` — `GET /v1beta/models`
returned 200 all through a real account restriction:

```bash
curl -s -o /dev/null -w '%{http_code}' -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent" -H "x-goog-api-key: $GOOGLE_API_KEY" -H 'Content-Type: application/json' -d '{"contents":[{"parts":[{"text":"say ok"}]}],"generationConfig":{"maxOutputTokens":2048}}'
```

**200** = go · **400 `FAILED_PRECONDITION`** = the exit IP, switch server ·
**403** = the account, a different exit will not help · **429** = quota.

*2026-09-17: `80.240.20.89`, AS20473 The Constant Company (Vultr, Frankfurt) —
200 on both keys. The ISP name is a HINT, never a verdict. Only the probe
decides.*

### The traps, and every one of them cost real time

| trap | what happens | what to do |
|---|---|---|
| **a heredoc mangles backslashes** | an escape in a patch script lands as a literal control character — a word-boundary escape became **0x08 BACKSPACE**. ruff passes, the import passes, and the regex silently matches nothing | write the patch to a **file** with the Write tool and run that file; then audit for control bytes |
| **flash-lite paces by REQUESTS, TOKENS bind** | a 50-document call on a 474-token corpus is ~24,700 tokens, and 250K TPM allows ~10 calls/min, not the 13/min the pace assumes | expect 70s backoffs on big-chunk corpora; one re-run slept ~23 minutes |
| **double backgrounding** | `cmd &` inside a backgrounded tool call is killed when the outer shell exits | no `&`; let the tool background it |
| **Gemma returns HTTP 500 on ~1 call in 3** | a hand-rolled retry loses whole runs | `LLMClient(chain=buckets(provider))` |
| **flash-lite's 500/day is spent** | every call stalls 70s then fails | `export GOOGLE_API_KEY="$GOOGLE_API_KEY_2"` — quota is per project per model |
| **`grep` in a pipeline buffers** | a background log shows nothing for ten minutes, then the process dies and the output is LOST | write the log UNFILTERED, filter when reading |
| **counting processes by script name** | always 0 — `ps` shows the interpreter path, not the script | count `labpilot/.venv/Scripts/python` instead |
| **`pkill` does not exist here** | a silent no-op, then two loops write to one log | list with `ps -W`, then `kill -9 <pid>` |
| **pre-commit stashes unstaged files** | an unstaged edit was silently lost once | stage everything before committing, and check the file survived |
| **the VPN link is the bottleneck** | three busy jobs cause SSL handshake timeouts | at most two jobs actively calling; jobs sitting in backoff are nearly free |

---

## 0.6 WHAT ELSE TO READ, and what NOT to read

| | |
|---|---|
| **`CLAUDE.md`** | **loads automatically** as project instructions. Do not re-read it wholesale — it is 15,600 lines |
| **this file** | the what, the why, the order. Read it fully |
| `docs/slice8v2/FINDINGS.md` **G14, G15, G18, G19** | read these four before touching the instrument — they are why the caches have the shape they do |
| `docs/slice8v2/DECISIONS.md` | the decisions being re-weighted, with the Python-backing table |
| the scripts | **read each one when you first run it**, not up front. Their docstrings carry the reasoning |
| `git log` | **not needed.** The commit messages are narrative, and every conclusion in them is also in the docs |

> **Do not front-load.** Reading every script and the whole git history before
> starting spends context on things most of which will never be touched. Read
> this file, those four findings, and then each script as you reach it.

## 1. WHY. The v2 zoo does not match the product

`docs/slice8v2/` measured **13 corpora**. Only **3** are Python or Jupyter:

```
PYTHON / JUPYTER   quora 82 · requests 335 · notebooks 382        3 of 13  (23%)
OTHER CODE         Go x3 · Rust · C · Java · TypeScript           7
PROSE              PDF · Word · Markdown                          3
```

**And the skew is worse than 23%, because it is self-reinforcing.** Python and
notebooks are the only inputs with a real splitter — AST and cells — so their
chunks are about half the size, retrieval is easier, and **two of the three sit
at `r@50` = 1.000, saturated.** A saturated corpus cannot show a gain. So every
measurement that had to pick a subset picked it by headroom, and **headroom
excluded Python automatically.**

### Measured: how much Python actually backs each v2 decision

| decision | corpora | Python | which |
|---|---|---|---|
| N = 20 (`VECTOR_TOP_N`) | 13 | 3 — 23% | quora, requests, notebooks |
| reranking ships | 13 | 3 — 23% | quora, requests, notebooks |
| `SKIP_MARGIN = None` | 13 | 3 — 23% | quora, requests, notebooks |
| no routing signal | 13 | 3 — 23% | quora, requests, notebooks |
| fusion: score beats wRRF | 13 | 3 — 23% | quora, requests, notebooks |
| **fusion THRESHOLD `r@50` < 0.95** | 3 | **0 — 0%** | **NONE** |
| **`SEARCH_LIMIT` = 50** | 4 | **0 — 0%** | **NONE** |
| **chain 3 / Cohere** | 3 | **0 — 0%** | **NONE** |
| embedder: codestral primary | 3 | 2 — 66% | quora, requests |
| `MIGRATION`: 001 above 2 | 4 | 2 — 50% | quora, requests |
| merged reranking rejected | 5 | 2 — 40% | quora, notebooks |

**Three decisions have ZERO Python behind them**, and they are the three that
needed a subset because they cost quota.

---

## 2. THE NEW ZOO — 20 corpora, 10 Python

**Keep all 13 existing corpora.** Add **7 Python**, spanning short to long, so
the Python side alone covers the whole size range the product will meet.

### The 7 to add

| # | corpus | source | ~chunks | why this one |
|---|---|---|---|---|
| P1 | **one notebook** | `research-notebooks/Titanic/` or `SMS Spam/` | ~80–150 | the smallest real unit a user uploads |
| P2 | **a small script app** | `apps/Disaster Twitts/` — 27 files, 2,338 lines | ~60–80 | scripts, not a library |
| P3 | **a mid script app** | `apps/sms-spam/` — 59 files, 3,483 lines | ~90–120 | the user's own, FastAPI-shaped |
| P4 | **a large app** | `apps/Lung Disease Detection/` — 137 files, 23,280 lines | ~550–700 | a real multi-module application |
| P5 | **a mid library** | web: `pallets/click` or `pallets/flask` | ~1,500–3,000 | a packaged library, not an app |
| P6 | **a LONG library** | web: `pytest-dev/pytest` — **9,929 chunks measured** | ~10,000 | the user's "+7k chunks" case |
| P7 | **a VERY long library** | web: `pydantic/pydantic` — **13,153** — or `dask/dask` — **11,527** | ~11,000–13,000 | the production ratio, see below |

*P6 and P7 chunk counts are not estimates — they were measured on 2026-09-05
and are recorded in CLAUDE.md under the index decision.*

**Two must come from the user's own work** (P2/P3/P4 above satisfy this; one
notebook from `research-notebooks/` satisfies P1). The user named both folders:

```
C:\Users\98922\Documents\python_scripts\AI\apps
C:\Users\98922\Documents\python_scripts\AI\research-notebooks
```

### Why P6 and P7 matter more than their size suggests

Every v2 run printed a line like *"the top-50 window is 7% of this corpus — at
a real 10,000-chunk artifact it would be 0.5%"*. **No corpus in the v2 zoo is
that artifact.** The largest is `zod` at 1,160.

At 10,000 chunks the top-50 window is **0.5%** — the real production ratio — and
`r@50` will fall a long way below the saturation ceiling. **P6 and P7 are the
first corpora that can measure retrieval at the size LabPilot actually targets**,
and they are Python.

### The resulting zoo

```
PYTHON / JUPYTER   10 of 20   ~60 -> ~13,000 chunks     THE TARGET, DOMINANT
OTHER CODE          7 of 20   Go x3, Rust, C, Java, TS  support, still measured
PROSE               3 of 20   PDF, Word, Markdown       support, still measured
```

---

## 2.5 THE REUSE RULE — run the 7 NEW corpora, never the 13 old ones

**This is the most important operating rule of the run, and it is nearly free.**

Every aggregate script globs `.logs/results/`:

```python
for path in sorted(RESULTS.glob("hybrid_*.json")):     # aggregate.py
for path in sorted(RESULTS.glob("rerank_*.json")):
```

`.logs/results/` is **gitignored and lives on disk**, so it is shared by every
branch and already holds all 13 corpora from v2. **Therefore:**

> **Run each measurement on the 7 NEW corpora only. The aggregates pick up the
> existing 13 automatically, and every table becomes a 20-corpus table with
> nothing old re-run.**

That is not a shortcut — it is the correct thing to do. The v2 numbers were
produced by the same scripts, on the same embedder, at the same settings, and
the instrument defect (G14) is already corrected in the files that survived.
Re-running them would spend quota to reproduce numbers we already hold.

### What to reuse, what to extend, what genuinely must be re-run

| measurement | v2 state | v3 action |
|---|---|---|
| retrieval / fusion / wording / kind | 13 corpora, valid | **EXTEND** — `score_hybrid.py` on the 7 new, then `aggregate.py`. FREE after embedding |
| reranking + the skip gate | 13 corpora, valid | **EXTEND** — `score_rerank.py` on the 7 new |
| N to send / `VECTOR_TOP_N` | 13 corpora, valid | **EXTEND** — `score_answers.py` on the 7 new, then `regrade_answers.py` and `dilution.py` re-read everything |
| tier reachability | all corpora, free | **EXTEND** — `tier_reach.py` reads the zoo directly |
| **fusion threshold** | **3 corpora, 0% Python** | **EXTEND with Python** — the new corpora ARE the fix |
| **`SEARCH_LIMIT` 30 vs 50** | **4 corpora, 0% Python** | **EXTEND with Python** |
| **Cohere vs flash-lite** | **3 corpora, 0% Python** | **EXTEND with Python**, and Cohere is 1,000 calls a MONTH |
| merged vs per-side | 3 pairs, 2 artificial | **ADD one Python+Python pair** |
| embedder ranking | 3–8 corpora | **EXTEND** only if cheap; codestral primary is settled on capability |
| exact vs HNSW | 12 artifacts, real instance | **REUSE AS-IS.** Nothing about the zoo changes a database benchmark |
| chunking `s`, `o`, header | 4–6 corpora | **REUSE AS-IS** unless a number looks wrong on the new corpora |
| `MIGRATION` order | 8 corpora | **REUSE AS-IS** — settled in G21 |

**Nothing in the "REUSE AS-IS" rows is re-run.** If a v3 number contradicts one
of them, that is a finding — investigate it, do not quietly overwrite it.

### One real hazard of sharing the results directory

`.logs/results/` is **not versioned**. Re-running an existing corpus
**overwrites** its JSON. The v2 *conclusions* are safe in `docs/slice8v2/`, but
the raw numbers are not.

**So before the first write, snapshot them:**

```bash
cp -r .logs/results .logs/results_v2_snapshot
```

Then a v3 run can never destroy a v2 number, and the two can be compared
directly.

---

## 2.6 THE SUBSET RULE — a subset must look like the zoo

Some measurements cannot run on all 20: Cohere is 1,000 calls a month, and a
45-query corpus at a fresh window is ~45 rerank calls. **Choosing a subset is
allowed and expected.** How it is chosen is the thing v2 got wrong.

> **Any subset must be AT LEAST HALF PYTHON, because the zoo is half Python and
> LabPilot is a Python and machine-learning tool.**

v2 chose its subsets by **headroom** — a defensible rule that produced three
decisions with **zero** Python behind them, because the Python corpora were
saturated and headroom excluded them automatically.

**The v3 rule, in order:**

1. **At least half the subset is Python or Jupyter.** Not negotiable.
2. Within that, prefer corpora with **`r@50` headroom** — a saturated corpus
   cannot show a gain.
3. Within that, prefer a **spread of sizes** — the new zoo runs ~60 to ~13,000
   chunks and a subset of three small ones measures nothing about a repository.
4. **State the composition beside the number**: not *"measured on 4 corpora"*
   but *"4 corpora, 2 Python, sizes 120 to 9,900"*.

If rules 1 and 2 conflict — if no Python corpus has headroom for some
measurement — **say so explicitly in the finding** rather than silently
dropping rule 1. That sentence is itself a result: it means the target language
cannot resolve that question, which is what this whole run exists to expose.

---

## 3. WHAT TO DO, IN ORDER

### Step 1 — build the fixtures FIRST. Nothing else until this is done.

For each of the 7: fetch or point at the source, chunk it, **draft ~20 queries
with a ground-truth file and line**, and validate.

```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/draft_queries.py <corpus>
PYTHONPATH=. .venv/Scripts/python.exe scripts/validate_fixture.py --all
```

**Four fixture rules, all learned the hard way — see `docs/slice8v2/FINDINGS.md`
G1, G3, G6:**

1. **INTERLEAVE the categories.** A fixture grouped by `asks` cannot be
   truncated — the first k queries become a category study wearing a corpus
   study's clothes. `geo` is the model to copy.
2. **A query must NEVER contain the identifier it is looking for**, or the run
   measures string matching.
3. **Every query needs a `file` field.** A repository has many files and line
   186 is in most of them.
4. **Label `asks` and `wording`** (`named` / `paraphrase`). Both are read by
   `aggregate.py --delta-by`.

### The fixture mechanics — the two things that are not obvious

**1. A corpus is DATA, not code.** It is a `corpus` block inside its own
`queries.json`, and `scripts/corpora.py` reads it. Nothing is registered by
editing a function:

```json
"corpus": {
    "key": "pytest",                    what the scripts call it
    "env": "LABPILOT_PYTEST_SRC",       the checkout, NEVER committed
    "include": ["**/*.py"],             globs, relative to that root
    "exclude": ["**/testing/**"],       globs, applied to the relative path
    "source": "relpath"                 how `file` in a query is spelled
}
```

Two fields carry traps, both documented at the top of `scripts/corpora.py`:

- **`key` names the embedding cache.** Renaming it later silently orphans the
  paid-for vectors. Choose the short name once.
- **`source` cannot be guessed.** A query's `file` must match `Chunk.source`
  exactly or its ground truth resolves to nothing — and the existing fixtures
  legitimately disagree: `requests` spells it `adapters.py` (one flat
  directory) while `geo` spells it `s2/cellid.go`. Decide it per fixture.

Also note `fnmatch` does **not** implement `**` the way you expect — that bug
made `cobra` 408 chunks including its own tests when it is really 193. See
**G1**.

**2. OUR OWN WALKER REFUSES A BIG REPOSITORY.**

```
MAX_FILE_BYTES    5,000,000     labpilot/sources/defaults.py
MAX_TOTAL_BYTES  20,000,000     <- this one bites
```

**Django was already refused this way** — it is recorded in CLAUDE.md under the
index decision. So check the size before drafting twenty queries against a repo
that cannot be ingested:

```bash
du -sm <checkout>          # must be under 20 MB of INCLUDED files
```

For reference, measured on 2026-09-05: FastAPI is 24,364 chunks and **14.7 MB**
of text, so the named candidates fit — `pytest` ~10 MB, `pydantic` ~13 MB,
`dask` ~12 MB. Anything larger needs a narrower `include`, and narrowing it is
a fixture decision to record, not a silent trim.

**Pin the commit.** `git clone --depth 1` then record repo, commit, licence in
the `queries.json`, exactly as the existing 13 do.


**Budget the embedding before starting.** 7 new corpora, the two large ones
dominating: roughly `10,000 + 13,000 + 4,000 = 27,000` chunks at ~340 tokens =
**~9M tokens**. On `codestral-embed` at a measured 554k tokens/minute that is
**~17 minutes** — but it is ~280 requests, so check the request ceiling too.
**Do NOT use Google for these**: it counts one TEXT as one request against
1,000 a day, so 27,000 chunks is 27 days.

### Step 2 — EXTEND every measurement to the 20-corpus zoo

**Run the 7 NEW corpora only — never the 13 old ones. See the reuse rule in
2.5.** The aggregates glob `.logs/results/`, so each table becomes a 20-corpus
table by itself.

**All of these are FREE** (they re-read caches and saved replies), so run them
first and read them before spending anything:

```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/score_hybrid.py <corpus> codestral
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --metric=MRR
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --delta-by=wording
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --by=format
PYTHONPATH=. .venv/Scripts/python.exe scripts/tier_reach.py --window=30
```

Then the ones that cost quota, **in this order** — the three with zero Python
backing come first:

| order | measurement | script | why first |
|---|---|---|---|
| **1** | **fusion threshold** | `score_hybrid.py`, `sweep_fusion.py` | 0% Python today, and P6/P7 finally give real headroom |
| **2** | **`SEARCH_LIMIT` 30 vs 50** | `score_rerank.py --window=30` | 0% Python today |
| **3** | **Cohere vs flash-lite** | `score_rerank.py --cohere` | 0% Python today; **1,000 calls a MONTH — state the bill before spending** |
| 4 | reranking + gate | `score_rerank.py` | 23% → must become ~50% |
| 5 | N to send | `score_answers.py`, `regrade_answers.py`, `dilution.py` | 23% → ~50% |
| 6 | merged vs per-side | `bench_merged.py` | add a Python+Python pair |

### Step 3 — the measurements v2 never ran at all

| # | measurement | cost |
|---|---|---|
| **A4** | **end-to-end TIME** — `WARN_MINUTES = 2.0` is still a guess | ~10 min |
| **new** | **`RERANK_TOP_N`** — v2 measured only the VECTOR path | ~78 calls |
| C3 | `rerank-3` (non-lite) — never scored anywhere | ~40 calls |
| C5 | a NEWER local reranker — the only tier that BATCHES | a download |
| C6 | `--no-header` under reranking | ~20 calls |
| D3 | ingest time vs `embedding_minutes()` | ~20 min |
| F2 | generated vs hand-written queries | ~8 calls |

### Step 4 — THE DECISION PASS. This is what the run is FOR, and it is not optional

**Measuring is not the deliverable. The deliverable is every decision, re-taken
on the 20-corpus evidence.** A session that finishes the runs and stops has not
finished.

Write **`docs/slice8v3/DECISIONS.md`**, and restate **every** decision — not
only the ones that changed. A decision that survives unchanged is a result, and
saying so is what makes the table trustworthy.

**One row per decision, with these columns:**

| column | what goes in it |
|---|---|
| decision | the shipped value |
| v2 said | the previous verdict |
| **v3 says** | **the verdict on 20 corpora** |
| corpora | how many, **and how many Python** |
| verdict | `CONFIRMED` · `CHANGED` · `OVERTURNED` · `STILL UNMEASURED` |
| evidence | the number, judged against what the fixture can resolve |

**The rows that must appear.** Anything missing from this list is a decision
that quietly kept its v2 value without being re-examined:

```
N to send / VECTOR_TOP_N          RERANK_TOP_N (v2 never measured it)
reranking ships, and which model  SKIP_MARGIN
SEARCH_LIMIT                      the per-tier rerank window
fusion: on or off, and the        fusion: which method
  r@50 threshold
merged vs per-side                routing by question kind
embedder primary                  MIGRATION order
exact vs HNSW                     chunk size s, overlap o, the header
end-to-end time / WARN_MINUTES    the two production defects
```

**Three rules for the pass:**

1. **A decision with no Python behind it must say so in its own row.** That was
   the whole problem with v2 and it must be visible per decision, not only in a
   summary.
2. **Say which v2 conclusions SURVIVED.** If N=20 still holds on 20 corpora
   with 10 Python, that is a stronger result than the v2 one and deserves to be
   written as `CONFIRMED`, not left implicit.
3. **A decision that cannot be taken is `STILL UNMEASURED`**, with what it would
   cost. Do not let an unmeasured thing inherit a value by silence — that is how
   `SKIP_MARGIN` and `RERANK_TOP_N` each carried an unexamined number for two
   whole runs.

**Then update, in this order:**

```
docs/slice8v3/DECISIONS.md   the decision table - write it FIRST
docs/slice8v3/FINDINGS.md    the evidence behind any decision that moved
docs/slice8v3/RESUME.md      the handoff, if anything is left open
CLAUDE.md                    the Current Status block, with the corrections
```

**CLAUDE.md is the last step and it is part of the job.** It carries the v2
warning block today; v3 must replace it, or the next reader acts on superseded
numbers.


---

## 4. WHAT MUST NOT BE REPEATED

**All v2 results are kept and are still valid for what they measured.** They are
in `docs/slice8v2/` — `RESULTS.md`, `FINDINGS.md` (G0–G21), `DECISIONS.md`,
`MEASUREMENTS.md`, plus `.logs/results/` and the caches. **Do not delete them.**
The v3 job is to re-weight them toward Python, not to discard them.

### Read these before touching the instrument

| | |
|---|---|
| **G14** | the rerank cache was broken for LISTWISE rerankers. A listwise entry is keyed by the **candidate set** in `*.orders.json`; an unseen set **raises**; a listwise call is **never split**. `.cache/rerank/void/` holds 8 quarantined caches — **do not restore them** |
| **G18** | **print the DENOMINATOR beside every ratio.** One error produced three different wrong conclusions in one session |
| **G15** | grading the citation on punctuation cost an entire column; raw replies are saved so a re-grade costs nothing |
| **G19** | `bench_merged` indexed both sides from zero and they shared a key space |

### The traps

They are in `docs/slice8v2/RESUME.md` §3 and they are all real:
a heredoc turning `\b` into a **0x08 backspace** that ruff accepts · flash-lite
pacing by requests when TOKENS bind · double backgrounding · Gemma's HTTP 500 ·
pre-commit stashing unstaged files · at most two jobs actively calling.

---

## 5. THE STANDING RULES FOR THIS RUN

1. **Judge a method by how many independent ways it was shown better**, never by
   its best single number.
2. **Report headroom beside every metric.** A saturated corpus cannot show a
   gain — that is the whole reason this run exists.
3. **Name the corpus AND the embedder** beside every number.
4. **Print the denominator, and judge a delta against what the fixture can
   resolve** — one query is `0.5 / queries` of MRR.
5. **NEW, and it is this run's reason to exist: state the PYTHON SHARE beside
   every conclusion.** *"Measured on 4 corpora"* is not enough any more; it must
   say *"4 corpora, 2 of them Python"*. A decision with zero Python behind it is
   a decision about other languages, and it must say so.

---

## 6. BRANCH AND HYGIENE

```
new branch     slice8/measure-final   OFF slice8/measure-v2   <- NOT off main
keep           docs/slice8v2/ and .logs/results/ untouched
write          docs/slice8v3/
main           ONLY the user commits to main
```

**The branch ALREADY EXISTS and is pushed** — created 2026-09-17 off
`slice8/measure-v2` at `6c0e35d`. Just check it out:

```bash
git checkout slice8/measure-final
git status          # expect: clean, up to date with origin
```

**OFF `slice8/measure-v2`, and this is not a preference.** `main` does not have
a single measurement script — `aggregate.py`, `score_hybrid.py`,
`score_rerank.py`, `score_answers.py`, `regrade_answers.py`, `dilution.py`,
`tier_reach.py`, `bench_merged.py`, `corpora.py`, `draft_queries.py`,
`validate_fixture.py`, `warm_embeddings.py` and the rest are all v2-only, 51
commits ahead.

> **Branching off `main` would lose the entire instrument — including the
> listwise cache fix (G14).** The run would then re-contaminate every listwise
> reranker measurement in exactly the way that voided five corpora, and the
> numbers would look fine.

Merging `slice8/measure-v2` into `main` first is the user's call and is not
required — branching off it works and keeps `main` untouched.

**Commit one piece at a time and push each** — one commit per module or finding,
suite green at each step. Run `pytest tests/unit tests/api -q` and both ruff
commands before every commit.

**Check the exit ISP before any call to a model.** `docs/slice8v2/RESUME.md` §1
has the two commands.

---

## 7. THE TWO PRODUCTION DEFECTS — still unfixed, and one breaks a SHIPPED decision

Deliberately not implemented: production code is the user's to write in this
project. The design is recorded so it is a decision, not a rediscovery.

**1. `MAX_BATCH_SIZE = 96` is a MISTRAL constant with a global name.** 96 Google
texts is ~32,800 tokens against a 30,000/minute ceiling — refused on the **first
batch** — and `embed_batches()` halves only on a refusal naming *tokens*, which
Google's does not. **Decision A8 shipped `SMALL_CORPUS_CHUNKS = 500`, routing
every small corpus to Google first, so the shipped routing cannot finish an
ingest.**

**2. `embedding_minutes()` counts HTTP calls where Google counts TEXTS**, and
models no daily request budget. It reports ~118 minutes for a 10,000-chunk
Google ingest; the truth is **ten days**.

**The fix already exists in the WRONG LAYER** — `scripts/warm_embeddings.py`
batches by tokens and paces by texts, citing findings F1 and F4 by name. So the
instrument's private workaround hides the product's defect.

**This matters more in v3 than it did in v2**, because P6 and P7 are 10,000+
chunk Python repositories — exactly the case that breaks.
