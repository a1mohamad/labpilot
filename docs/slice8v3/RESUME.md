# SLICE 8 v3 — RESUME. Read this, then `FINDINGS.md`.

**READ THIS FILE ONLY.** It is self-sufficient. `FINDINGS.md` has the
long-form evidence (H0–H11) and is optional detail; `MISSION.md` is the
original brief and is now PARTLY SUPERSEDED by §1 and §6.

Branch **`slice8/measure-final`**, off `slice8/measure-v2`. Suite **752 passed,
4 skipped**, ruff clean. **Never commit to `main`.**

---

## 0. SET UP THE SESSION

```bash
cd "C:/Users/98922/Documents/python_scripts/AI/apps/labpilot"
set -a; source .env; set +a      # API keys
source .corpora/env.sh           # WHERE each corpus lives (gitignored)
PYTHONPATH=. .venv/Scripts/python.exe -u scripts/...   # -u or logs buffer
```

`python` is a 3.10 without our deps. Always `.venv/Scripts/python.exe`.
**Probe the exit ISP before any model call** — `MISSION.md` §0.5 has the two
commands. Last good exit: `176.119.150.78`, AS43357 Owl Limited, Frankfurt,
**200 on both Google keys**.

---

## 1. WHAT THE RUN IS FOR — and how the brief CHANGED

The mission was: rebuild the zoo so Python dominates, then re-take every
decision on it. **The user then sharpened it twice, and both are binding:**

> **1. Do not RE-TEST v2's chosen values — SEARCH the space again.** A config
> inherited from a different corpus population is an assumption wearing a
> number's clothes. This was a real failure: H1–H10 all ran `score_hybrid`
> with **no flags**, pinning every knob at v2's winner.

> **2. Every measurement, on the new zoo — free, cheap, medium AND expensive.**
> Reuse a v2 number only where the sub-measurement would be an exact repeat.

Standing rules, unchanged: state the **Python share** and the **difficulty
range** beside every conclusion (`scripts/zoo.py --difficulty`), print the
**denominator**, and judge a delta against what the fixture can **resolve**
(one query = 0.050 MRR at 20 queries; the bar used throughout is **1.5
queries**).

---

## 2. THE ZOO — 20 corpora, 10 Python (50%), 423 queries

Built this run, all verified: `scripts/validate_fixture.py --all` → ALL OK.

```
NEW (7, all Python)  titanic 118 · disaster 108 · smsspam 89 · lung 628
                     click 1585 · pytest 6714 · pydantic 9846
PAIRED HAND (3)      pydantichand · pytesthand · lunghand
```

**The three hand fixtures are for ONE purpose**: comparing hand-written with
LLM-drafted queries **on the same corpus**. Never compare one with a
*different* corpus — their difficulty is not calibrated to the zoo. Cross-corpus
work uses the 20 drafted fixtures.

`.logs/results_v2_snapshot/` holds the 88 v2 result files, taken before the
first v3 write. `.logs/results/` is shared across branches and **not
versioned** — re-running a corpus overwrites its JSON.

---

## 3. DONE — every measurement re-run on the new zoo

| # | measurement | scope | verdict |
|---|---|---|---|
| 1 | fusion method + params | **51 settings** × 20 corpora | `score a=0.85` **#1 of 51** — CONFIRMED, earned |
| 2 | BM25 `k1`/`b` | 6 × 20 — **first sweep ever** | `1.2,0.75` #1, but all six within 0.0037 → **indistinguishable** |
| 3 | embedder codestral vs mistral | 20 corpora | **codestral 19–0–1**, 0.634 vs 0.514 |
| 4 | **fusion on/off** | 20 corpora | **CHANGED → ALWAYS ON.** +8.7 queries, **0 corpora harmed** |
| 5 | reranking helps? | 16 corpora @ w50 | 9 real gains, **0 real losses** |
| 6 | tier reachability | 20 corpora | Gemma serves **10/10 Python**, 0/9 non-Python |
| 7 | query provenance | 3 paired | **difficulty, not provenance** — matched pair identical |
| 8 | chunk size `s` | 7 corpora (3 Python) | **`s=500`** — Python 0.606, all 0.614 |
| 9 | **`MIGRATION` order** | 4 corpora | **FIXED IN CODE** — see §4 |
| 10 | Cohere / gemini-2 on new Python | 5 corpora | nobody dominates — see §5 |
| — | exact vs HNSW | — | **reused from v2 on purpose**: a database benchmark, corpus-independent |

### The one decision CHANGED so far (#4), and why it matters

v2 shipped *"fuse when `r@50` < 0.95"*. **That is not implementable** — `r@50`
needs ground truth, which a user's repo never has, and no proxy predicts it
(`pydantic` at 9,846 chunks is saturated; `geo` at 729 is not).

Measured instead: **always-on `score a=0.85`** gains ≥1 query on 5 corpora,
loses ≥1 query on **none**, net **+8.7 queries MRR / +6.0 r@50** of 423.
Cost: ~1,022 bytes/chunk (+12% of a 1536-dim row) and 4–5 DB round trips,
because Postgres has no BM25 and we compute it in Python.

**BM25 stays** — it is the *keyword ranker*, a different layer from *fusion
method*. `ts_rank` loses on all 20 and must not be substituted for it.

---

## 4. CODE CHANGED THIS RUN

**`labpilot/embed/registry.py` — `MIGRATION` order fixed.** `gemini-embedding-2`
sat above `001` on **Google's** MTEB numbers, not ours; the file's own comment
said so and said "slice 8 owes this model a score". v2's G21 scored it, it
lost, **and the code was never changed** — so for a whole run the routing
preferred the weaker model. 001 now sits above 2. Measured: 001 beats 2 on
**3 of the 4** corpora where both ran. The guarding test
`test_the_measured_google_embedder_outranks_the_one_google_prefers` was
rewritten and **mutation-verified** (reverting the tuple fires it alone).

**`labpilot/embed/base.py` + `contracts.py` — THE EMBEDDER GATE WAS BLIND
TO GOOGLE.** `embedding_minutes()` returns `inf` for a model that cannot finish
today and `_pick_embedder` skips those. That worked for BGE (a token budget) and
NOT for Google, whose limit is neither tokens nor calls: **one TEXT is one
request**, so a 96-text batch spends 96 of the day's 1,000.

```
BEFORE  20,000 chunks -> Gemini reports 163 min   (truth: 20 DAYS)
AFTER    2,000 chunks -> CANNOT TODAY, drops out of the walk
         1,000 chunks -> still runs
```

Hit twice on 2026-09-18 while running into it: a `gemini-embedding-2` warm died
with a 429 on its SECOND corpus, and `001` exhausted after 943 chunks. This was
v2's production defect #2. `Rate` gains `daily_text_budget`; both Google models
set it to 1,000.

**Cohere checked and deliberately NOT given one** — it bills per CALL at up to
96 texts, so its 1,000 a month is a caller's budget question, not a per-ingest
refusal. Its `tokens_per_minute` was corrected 640,000 → 100,000 (the measured
trial cap; 640,000 was a burst that never met a limit).

**`MIGRATION` REORDERED on measured strength**, 2026-09-18:

```
BEFORE  codestral, BGE, mistral, google-001, cohere, google-2
AFTER   codestral, BGE, google-001, cohere, google-2, mistral
```

mistral-embed sat THIRD and loses to every embedder it has been compared with —
1 win of 7 vs google-001, 3 of 13 vs cohere, 4 of 11 vs google-2. It stays in
the list only because it is the only model that can ingest 10,000 chunks
quickly; a walk must not dead-end. Both changes mutation-verified.

Also added: `scripts/zoo.py` (Python share + `--difficulty`),
`scripts/query_difficulty.py` (per-fixture query difficulty),
`scripts/tier_reach.py` order() derived from the zoo instead of a hardcoded 13,
and a seventh check in `validate_fixture.py` (`degenerate`).

---

## 5. RESULTS THAT LANDED AFTER §3 WAS WRITTEN

**Nothing is running any more.** Check `ls .logs/results/` before re-running:
if a result file exists, that measurement is done.

### RERANK_WINDOW — MEASURED, and it CHANGES from 50 to 20

Six windows, 5 corpora, **100% Python, 89 to 9,846 chunks**, flash-lite:

| corpus | chunks | w5 | w10 | w20 | w30 | w40 | w50 | best |
|---|---|---|---|---|---|---|---|---|
| smsspam | 89 | +0.147 | +0.222 | +0.264 | +0.234 | **+0.277** | +0.180 | w40 |
| lung | 628 | +0.011 | **+0.099** | +0.054 | +0.030 | +0.019 | −0.004 | w10 |
| click | 1585 | −0.021 | −0.023 | **+0.011** | +0.000 | — | +0.008 | w20 |
| pytest | 6714 | −0.013 | **+0.129** | +0.123 | +0.123 | +0.117 | +0.081 | w10 |
| pydantic | 9846 | **+0.079** | +0.049 | −0.003 | +0.033 | −0.016 | +0.002 | w5 |

```
w10 +0.095   w20 +0.090   w30 +0.084   w50 +0.053   w5 +0.041
(w40 shows +0.099 on 4 corpora, missing click - flattered)
```

**The shipped w50 is nearly HALF as good as the best.** w10/w20/w30 are
indistinguishable (+1.84/+1.76/+1.67 queries, spread 0.17 queries — below
resolution). **Recommend `RERANK_WINDOW = 20`**: middle of the flat region,
fewer tokens per call so more tiers reachable, within noise of the best.

**The per-corpus optimum is everywhere** — w5, w10, w20 and w40 each win on
some corpus, and the spread WITHIN a corpus (pydantic +0.079 at w5, −0.016 at
w40) exceeds the spread between window means. A global window is a compromise.

Note what `--window` actually is, verified in the source
(`vector_candidates = dense[q.id][:window]`): it is how many of the searched
chunks the **reranker sees**, i.e. `RERANK_WINDOW`. It is NOT `SEARCH_LIMIT`.

```
search        -> 50   SEARCH_LIMIT
top 20 of 50  -> 20   RERANK_WINDOW   <- this is what was measured
reranked, send-> 10   RERANK_TOP_N    <- still unmeasured
```

### SEARCH_LIMIT — the COST measured, the benefit is nil, so KEEP 50

Never swept in v2 or v3. It is a **hard ceiling**: an answer outside it can
never be recovered by fusion or reranking. Over 20 corpora, vector alone:

| SEARCH_LIMIT | mean recall | queries lost of 423 |
|---|---|---|
| 10 | 0.864 | **45** |
| 20 | 0.930 | 16 |
| 25 | 0.951 | 8 |
| 30 | 0.957 | 5 |
| **50** | **0.968** | 0 |

The only thing lowering it buys is time, and exact search is ~11 ms at 1,387
rows against a 350 ms VPN round trip. **No trade to make — keep 50.** Going
ABOVE 50 is the untested direction and is not free.

### Routing by question kind — CONFIRMED DEAD on the new zoo

16 corpora, 10 Python, flash-lite w50. **Every kind positive**: error +0.152,
api +0.140, structure +0.090, behaviour +0.089, constant +0.019, claim +0.303
(n=10), checklist +0.151 (n=7). The worst single cell is `structure −0.500` on
`websocket` with **n=1** — G18's denominator trap reproducing exactly.

### SMALL_CORPUS_CHUNKS — DELETED FROM THE CODE

See §4. Measured on six corpora against `gemini-embedding-001`: three wins
each, net codestral ahead 0.023 MRR ≈ half a query, below resolution. Deleted
rather than retuned to 200, because a rule that exists to buy quality and buys
none has no threshold that fixes it.

### DUAL-EMBEDDER FUSION — explored on the user's prompt, then PARKED

Free experiment over cached vectors: fuse two embedders' rankings with RRF, the
way vector and BM25 are fused. 8–12 corpora.

| | mean MRR | mean r@50 |
|---|---|---|
| codestral alone | 0.6457 | 0.9596 |
| google-001 alone | 0.5898 | 0.9778 |
| cohere alone | 0.6050 | 0.9714 |
| codestral + cohere | 0.6412 | 0.9788 |
| **codestral + google** | **0.6664** | 0.9743 |
| ORACLE (best of two per query) | **0.7172** | 0.9812 |

**The insight worth keeping: Google ALONE is worse than codestral, but Google
ADDED to codestral is better.** That is exactly why the deleted routing rule
failed — it *substituted* where it should have *added*. And the ORACLE gap
(+0.085 MRR over codestral) proves the embedders fail on genuinely different
queries; RRF captures only part of it.

**PARKED, and the user agreed it is not worth it now:**
- under 200 chunks both fusions are **3 of 6** — a coin flip, and `r@50` is
  already 0.9917, so there is nothing left to find;
- gains concentrate on LARGER corpora (`geo`, `lung`: r@50 0.8745 → 0.9222),
  where the quota does not stretch;
- ingest cost: +cohere 0.81 min at 500 chunks (silent), **+google 4.3 min
  (trips WARN_MINUTES)**. Cohere is 5x faster than Google; its blocker is the
  1,000-calls-a-MONTH budget, not time;
- `pytest` and `pydantic` have **no Cohere or Google vectors at all**.

Revisit only if a paid Cohere or Google tier appears. It is a Step 2 idea, not
a slice 8 decision.

## 6. STILL TO MEASURE

| # | measurement | cost | note |
|---|---|---|---|
| B | **`VECTOR_TOP_N` / `RERANK_TOP_N`** | **~390 GENERATION calls** | **nothing has measured these in v2 OR v3** |
| C | chunk **overlap** `o` and **header** on Python | re-embed per variant | v2 has non-Python only |
| D | chunk size on **pytest** | re-embed | crashed at 5,760/9,839 on a Mistral 503 |
| E | **reranker model** comparison on new Python | flash-lite + gemma + voyage | v2 ranked 9 configs on the old zoo. NOTE: `tier_reach` now shows Gemma serves 10/10 Python corpora at w50 (v2 said 4 of 13), so chain 3's BUDGET reasoning was wrong even if its order is right |
| F | **BGE embedder** | never run **ANYWHERE**, in v2 or v3 | **SEE BELOW — this is the biggest hole** |
| G | all-suffix corpus check | re-embed 1 corpus | see below |

### B is the most important, and the shipped value is probably wrong

```
VECTOR_TOP_N = 25   shipped   <- v2 said "should be 10, not 25" and NEVER SHIPPED IT
RERANK_TOP_N = 10   shipped   <- never measured, by anyone
```

v2's top-N evidence (`answers_flashlite.json`) is **13 corpora, 3 Python**,
none above 1,160 chunks — and v2 flagged its own run as measuring the
**degraded** path only (`chosen()` uses `dense_orders`; no reranker touches
it), which is why it can speak to `VECTOR_TOP_N` and not `RERANK_TOP_N`.

### F — BGE SITS AT POSITION 2 AND HAS NEVER BEEN SCORED

**`@cf/baai/bge-base-en-v1.5` is second in `MIGRATION` and no corpus has ever
been embedded with it — not in v2, not in v3.** It is there on a PLATFORM
argument: codestral and mistral-embed share one API key, so a Mistral outage
would otherwise take the top two. That is a robustness argument sitting in a
tuple whose own comment calls it "the strength order".

**So if codestral fails, the fallback is an unmeasured model.**

Two things make it awkward rather than simply undone:
- its `max_input_tokens` is **512**, and its real tokenizer runs 1.12–1.45x our
  `chars/3` estimate, so some chunks may be silently truncated. v3 measured the
  ratio but never the recall.
- `daily_token_budget = 684,000` (10,000 Cloudflare neurons), so it reports
  CANNOT TODAY above ~2,900 chunks — it can only be measured on the small and
  mid corpora anyway.

**Cost to close it: cheap.** Warm + score the small/mid Python corpora
(`smsspam` 89, `disaster` 108, `titanic` 118, `lung` 628, and `click` 1585 if
the budget allows) — neurons only, no generation quota:

```bash
bash <scratch>/warm_model.sh <log> "@cf/baai/bge-base-en-v1.5" smsspam disaster titanic lung
PYTHONPATH=. .venv/Scripts/python.exe -u scripts/score_hybrid.py smsspam bge
```

If it scores badly, position 2 is wrong and the platform argument needs a
different model behind it.

### G — the one place the corpora do NOT match real usage

The user accepted `.py`-only as correct for a Python-focused run, and
confirmed corpora are **never subsampled** (all 9,846 of pydantic's chunks are
embedded and searched; only the *query count* is 20). What remains open: a real
ingest reads **58 suffixes**, so pydantic would be **13,377** chunks, not 9,846
(+36%), and pytest 9,653 not 6,714 (+44%). Re-chunking one corpus with all
readable suffixes and re-scoring would show whether mixed-format content
changes retrieval. Cheap: ~2 min of embedding.

Two corpora were also narrowed to remove **machine-generated duplicates** —
`lung` dropped `**/mlflow/artifacts/**` (34.8% duplicate chunks, one repeated
16×) and `pydantic` dropped `tests/mypy/outputs/**` (6.6%). Those were breaking
ground truth: a query anchored to one of a dozen identical copies is
unanswerable by fair retrieval. Defensible, and recorded on each corpus block.

---

## 7. USER DECISIONS TAKEN — do not re-litigate

1. **Reranker order and embedder order in the chains are fine** — do not
   re-measure chain 3's order or `MIGRATION`'s full ranking. (The 001-vs-2
   *pair* was a separate, already-fixed defect.)
2. **Control for query difficulty and report it; do NOT re-draft ~400 queries**
   to a uniform target. Re-drafting would mean discarding queries by a
   retrieval-adjacent metric, which is close to building a fixture that agrees
   with our own embedder.
3. **`SMALL_CORPUS_CHUNKS` should probably drop 500 → 200** — pending the
   gemini-001 result. The speed case is already made, see §8.
4. `.py`-only corpora are correct for this run's purpose.

---

## 8. `SMALL_CORPUS_CHUNKS` — the argument, pending one number

Shipped: `= 500`, routing corpora under that to Google first
(`labpilot/api/services.py:225`).

**Google is 19× slower than codestral at every size**, and `WARN_MINUTES = 2.0`
is where the product stops and asks the user to confirm:

```
chunks   google   codestral
   150    1.2 min   0.06     silent
   200    1.6 min   0.09     silent
   240    2.0 min   0.10     <- the line
   500    4.1 min   0.21     WARNS THE USER
```

**At the shipped 500 the router picks an embedder that trips its own warning.**
Google is also 1,000 texts/day per key (2,000 across both), so a threshold of
500 allows ~4 small ingests a day; 200 allows ~10.

**Quality is the open half.** On `001` — the model that matters after the §4
fix — the evidence is 3 corpora, **1 win each and a tie**: websocket 0.530 vs
codestral 0.668, quora 0.674 vs 0.608, requests 0.650 vs 0.646. The running job
adds 4 Python corpora.

- **Google wins on Python** → keep the rule, drop the threshold to **200**.
- **Google does not win** → **delete the rule**; codestral first, always.

---

## 9. TRAPS LEARNED THIS SESSION — all cost real time

| trap | what happens |
|---|---|
| **`score_hybrid` with no flags** | pins every fusion knob at v2's winner. `--sweep` and `--sweep-bm25` exist |
| **a hardcoded corpus list** | `tier_reach.py` had one; the 7 new corpora were silently missing from its table |
| **`sweep_chunking` saves only at the END** | a Mistral 503 at 5,760/9,839 chunks lost the whole run. It also **overwrites** its results file — back it up first |
| **the query cache is keyed by COUNT, not content** | 20 new queries silently reuse the old 20 vectors. Delete `*_queries.pkl` after editing a fixture |
| **Google paces per PROCESS** | `warm_embeddings` paces 100 texts/min *within* a run; the next corpus starts in the same window and 429s. Sleep 75s between corpora |
| **Python buffers stdout to a file** | use `-u`, or a background log shows nothing for ten minutes |
| **a listwise rerank cache is keyed by CANDIDATE SET** (G14) | a new window or `--fusion` is a **fresh call at full price**, never a cache hit |
| **3 jobs over the VPN** | SSL EOF. Two actively calling is the limit; it killed a sweep today |

---

## 10. THE DELIVERABLE

**`docs/slice8v3/DECISIONS.md` is not written yet, and it is the point of the
run.** One row per decision, restating **every** decision — not only the ones
that moved — with columns:

```
decision | v2 said | v3 says | corpora (and how many PYTHON) | DIFFICULTY RANGE
         | verdict: CONFIRMED / CHANGED / OVERTURNED / STILL UNMEASURED
         | evidence, judged against what the fixture can RESOLVE
```

A decision with no Python behind it must say so **in its own row**. A decision
that cannot be taken is `STILL UNMEASURED` **with what it would cost** — do not
let an unmeasured thing inherit a value by silence.

Then `FINDINGS.md`, then **`CLAUDE.md`'s Current Status block**, which still
carries the v2 warning and will otherwise send the next reader to superseded
numbers.
