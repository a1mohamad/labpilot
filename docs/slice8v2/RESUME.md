# RESUME HERE — slice 8, second run

> ## ⚠ THIS RUN IS SUPERSEDED — READ `docs/slice8v3/MISSION.md` FIRST
>
> Everything here is **valid for what it measured** and is kept on purpose.
> But the zoo is **3 Python corpora of 13 (23%)**, and LabPilot is a Python and
> machine-learning tool. **Three decisions here have ZERO Python behind them** —
> the fusion threshold, `SEARCH_LIMIT`, and chain 3 / Cohere.
>
> **The next run rebuilds the zoo to 20 corpora with 10 Python** (short scripts
> to a 13,000-chunk library) and re-weights every conclusion. The complete brief
> is `docs/slice8v3/MISSION.md` — a fresh session needs nothing else.



Everything a fresh session needs. Read this file first, then `DECISIONS.md`
(what is settled and what was corrected), then `MEASUREMENTS.md` (the coverage
checklist) and `FINDINGS.md` (the evidence, G0–G20).

**Branch `slice8/measure-v2`, pushed. `main` is untouched and must stay that
way — only the user commits to `main`.**

**Last session: 2026-09-17 (third).** It began by finding the measurement
instrument broken, and most of what follows is downstream of that.

---

## 1. Set the session up — this exact incantation

Nothing works without all four parts.

```bash
cd "C:/Users/98922/Documents/python_scripts/AI/apps/labpilot"
set -a; source .env; set +a      # API keys
source .corpora/env.sh           # WHERE each corpus lives (gitignored)
# and every command below needs BOTH of these:
PYTHONPATH=. .venv/Scripts/python.exe ...
```

**`python` is NOT the right interpreter.** It resolves to a 3.10 without our
dependencies. Always `.venv/Scripts/python.exe`.

**Before any command that calls a model**, probe the exit — the user is on a
VPN and Google refuses some exits:

```bash
curl -s https://ipinfo.io/json
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent" \
  -H "x-goog-api-key: $GOOGLE_API_KEY" -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"say ok"}]}],"generationConfig":{"maxOutputTokens":2048}}'
```

200 = go. 400 `FAILED_PRECONDITION` = the exit IP, switch server. 403 = the
account. 429 = quota. *2026-09-17: `80.240.20.89`, AS20473 The Constant Company
(Vultr, Frankfurt) — 200 on both keys.*

---

## 2. ⚠ READ THIS BEFORE TRUSTING ANY RERANK NUMBER

**The rerank cache was broken for LISTWISE rerankers and five of thirteen
corpora were void.** Fixed 2026-09-17 — see **FINDINGS G14**.

A listwise reranker (any Gemini or Gemma tier) returns an **order**, not
scores. `PairScores` synthesised one from the place, so every call produced the
same numbers 50…1 and two calls for one query collided.

**The rule is now structural and the code enforces it:**

- a listwise entry is keyed by the **candidate set**, in `*.orders.json`
- an unseen set **raises** instead of being stitched together
- a listwise call is **never split**
- fetch is per candidate set, never over the union

**`.cache/rerank/void/` holds the eight quarantined caches.** Do not restore
them. If you see a bare `<corpus>_<gemini|gemma>*.json` (no `.orders`), it is
pre-fix and must not be read.

---

## 3. Traps that cost real time — do not rediscover them

| trap | what happens | what to do |
|---|---|---|
| **a heredoc mangles backslashes** | `\\b` in a patch script lands as a literal **0x08 backspace**. ruff passes, the import passes, and the regex silently matches nothing | write patch scripts to a **file** and run that file; audit for control bytes afterwards |
| **flash-lite paces by REQUESTS, but TOKENS bind** | `PACE = 4.5s` is 13/min against a 15 RPM limit — but a 50-document call on a 474-token corpus is ~24,700 tokens, and 250K TPM allows only ~10/min. The geo re-run slept ~23 minutes in 70s backoffs | expect it; pacing should be computed from the call size, not fixed per model |
| **double backgrounding** | `cmd &` inside a `run_in_background` tool call is killed when the outer shell exits | let the tool background it; no `&` |
| **Gemma returns HTTP 500 on ~1 call in 3** | a hand-rolled retry loses whole runs | use `LLMClient(chain=buckets(provider))` |
| **flash-lite's 500/day is spent** | every call stalls 70s then fails | `export GOOGLE_API_KEY="$GOOGLE_API_KEY_2"` — per project per model |
| **`grep` in a pipeline buffers** | a background log shows nothing, then the process dies and the output is LOST | write the log UNFILTERED, filter when reading |
| **`ps -W \| grep -c score_answers`** | always 0 — `ps` shows the interpreter path | `grep -c 'labpilot/.venv/Scripts/python'` |
| **`pkill` does not exist** here | a silent no-op, then two loops write one log | `ps -W`, then `kill -9 <pid>` |
| **pre-commit stashes unstaged files** | an unstaged edit was silently lost once | stage everything before committing |
| **the VPN link is the bottleneck** | three busy jobs → SSL handshake timeouts | at most two jobs actively calling; jobs in backoff are nearly free |

---

## 4. WHAT IS SETTLED — do not re-measure these

Full evidence in `FINDINGS.md`; decisions in `DECISIONS.md`.

| | |
|---|---|
| **N to send** | **20 chunks.** N is a **COUNT**, not a coverage share (cv 0.41 vs ~1.0 over a 15× size range). Vindicates `RERANK_TOP_N = 10` **per side**; `VECTOR_TOP_N = 25` is too large |
| **reranking** | ships. 9 REAL gains, 1 REAL loss, 3 nothing — against each fixture's resolution |
| **the skip gate** | **OFF.** `SKIP_MARGIN = None`; 0.05 is overturned. Best global tau is +2.4 queries in 286 |
| **merged reranking** | **rejected.** Starves a side on **43 of 57** queries |
| **fusion** | on below `r@50` ≈ 0.95, off above — and the method is **score fusion**, not wRRF |
| **routing by question kind** | **no signal.** Every kind positive; slice 6's −0.534 was one query |
| **embedders** | top three within **0.012** on the corpora all five reached |
| **exact search** | ships; crossover ~700 rows |
| **chunking** | `s = 500`, header stays, `o = 25` beats 50 |

---

## 5. WHAT IS STILL OPEN

### 5.1 Running when the last session ended — CHECK THESE FIRST

```bash
tail -30 .logs/window30.log     # window=30 on jq, papers, gson, geo
tail -30 .logs/embed2.log       # gemini-embedding-2 on 5 more corpora
```

**The window-30 question, and why it is the one worth finishing:**
`scripts/tier_reach.py --window=30` shows that at window 30 **both Gemma tiers
serve all 13 corpora instead of 4** — 28,800 calls a day against Flash-Lite's
1,000. So the question is not "what is the best window" but **"what does
cutting to a window Gemma can serve actually cost"**. Compare each corpus's
`w30` result against its `w50` one.

**`gemini-embedding-2`:** its rank rests on 3 corpora, 2 saturated. On the only
unsaturated one (`geo`) it is **17 queries behind** codestral on a 45-query
fixture. Five more corpora settle it. Google counts one TEXT as one request
against 1,000 a day, so the run is 884 texts = one day.

### 5.2 Not started

| # | measurement | cost | why it matters |
|---|---|---|---|
| **A4** | **end-to-end TIME** | ~10 min | `WARN_MINUTES = 2.0` is still a guess and `services.py` says so |
| C3 | `rerank-3` (non-lite) | ~40 calls | never scored anywhere |
| C5 | a NEWER local reranker | a model download | `ms-marco-MiniLM` is 2021 and measured harmful. The local model is the **only** one that batches, which is what `verify` needs at one call per claim |
| C6 | the chunk header under reranking (`--no-header`) | ~20 calls | died on quota twice |
| D3 | ingest TIME per embedder vs `embedding_minutes()` | ~20 min | |
| F2 | generated queries vs hand-written | ~8 calls | the domain-lock fix, unmeasured |
| F4 | model blind spots are disjoint | a few calls | |
| **D8** | **fold all of it into CLAUDE.md** | — | **nothing from either session is written there yet** |

---

## 6. ⚠ TWO PRODUCTION DEFECTS, and one breaks a SHIPPED decision

**Deliberately not implemented.** This is a learning project and production
code is the user's to write — the design is recorded so it is a decision rather
than a rediscovery.

**1. `MAX_BATCH_SIZE = 96` is a MISTRAL constant with a global name.** It is
`floor(50,000 / 510)` from codestral's per-minute tokens and is used in three
places as if universal. At the measured mean of 341.6 tokens per chunk, 96
Google texts is ~32,800 tokens against a 30,000/minute ceiling — refused on the
**first batch**. `embed_batches()` halves only on a refusal containing the word
*token*, and Google's does not, so it **raises instead of halving**.

> **Decision A8 shipped `SMALL_CORPUS_CHUNKS = 500`, routing every small corpus
> to Google first. So the shipped routing cannot complete an ingest.**

**2. `embedding_minutes()` counts HTTP calls where Google counts TEXTS**, and
models no daily request budget at all. It reports ~118 minutes for a
10,000-chunk Google ingest; the truth is **ten days**.

**The design both need:** `max_batch_size` and the unit of account move onto
the embedder (`Spec` / `Rate`) instead of a module-level constant, and `Rate`
gains a daily **request** budget beside its daily token budget.

**And the fix already exists — in the wrong layer.** `scripts/warm_embeddings.py`
batches by TOKENS against a per-request budget and paces by TEXTS per minute,
with comments citing findings F1 and F4 by name. So the knowledge is in the
repository; it is just in the measurement script rather than in `embed/`, which
is why every measurement run succeeds and the shipped ingest path would not.

> **A workaround in the instrument hides a defect in the product.** The script
> is the only caller that exercises Google at scale, so its private fix makes
> the bug invisible exactly where it would otherwise have been caught.

---

## 7. Reading the numbers

```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --metric=MRR
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --rerank
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --gate
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --delta-by=wording
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --delta-by=kind
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --by=format
PYTHONPATH=. .venv/Scripts/python.exe scripts/regrade_answers.py
PYTHONPATH=. .venv/Scripts/python.exe scripts/dilution.py
PYTHONPATH=. .venv/Scripts/python.exe scripts/tier_reach.py --window=30
PYTHONPATH=. .venv/Scripts/python.exe scripts/validate_fixture.py --all
```

**Everything above costs NOTHING** — it re-reads `.logs/results/`, the caches
and the saved replies.

### The four rules these obey

1. **Judge a method by how many independent ways it was shown better**, never
   by its best single number.
2. **Report headroom beside every metric.** 7 of 13 corpora are saturated at
   `r@50 = 1.000` and cannot show a recall gain. Slice 5 decided fusion on two
   of those; slice 6 decided the gate on one.
3. **Name the corpus AND the embedder** beside every number.
4. **Print the DENOMINATOR beside every ratio**, and judge a delta against what
   the fixture can resolve. One query is 0.042 MRR on the 12-query `docx` and
   0.011 on the 45-query `geo`. *This one error produced three different wrong
   conclusions in one session* — see **G18**.

---

## 8. The zoo

13 corpora, 9 languages and formats, 286 queries, **nothing committed** — each
`queries.json` names its repo, commit, licence and env var.

```
websocket  78 Go      quora     82 Py+MD   docx     85 Word
log       146 Rust    cobra    193 Go      requests 335 Py
notebooks 382 ipynb   papers   404 PDF     docs     463 MD
jq        693 C       geo      729 Go      gson     750 Java
zod      1160 TS
```

Fetch with `git clone --depth 1` at the commit each fixture names, then point
`.corpora/env.sh` at the checkouts. `scripts/validate_fixture.py --all` proves
they are intact.

**Caches are paid-for data, not results.** `.cache/hybrid/` holds the vectors,
validated to `|1 − cos| = 3e-10`; `.cache/rerank/*.orders.json` holds listwise
rankings keyed by candidate set.

---

## 9. Suite state

```
752 passed, 4 skipped   (tests/unit + tests/api)   ruff clean both ways
```

Smoke tests were **not** run — they spend live quota and need the ISP probe.
