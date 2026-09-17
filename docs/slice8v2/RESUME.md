# RESUME HERE — slice 8, second run

Everything a fresh session needs to finish this work. Read this file first,
then `DECISIONS.md` (what is settled and what was corrected), then
`MEASUREMENTS.md` (the coverage checklist).

**Branch `slice8/measure-v2`, pushed, 22 commits. `main` is untouched and must
stay that way — only the user commits to `main`.**

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
dependencies — `pypdf`, `psycopg`, `requests` are all missing there. Always
`.venv/Scripts/python.exe`.

**Before any command that calls a model**, probe the exit — the user is on a
VPN and Google refuses some exits. This is CLAUDE.md's standing rule:

```bash
curl -s https://ipinfo.io/json
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent" \
  -H "x-goog-api-key: $GOOGLE_API_KEY" -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"say ok"}]}],"generationConfig":{"maxOutputTokens":2048}}'
```

200 = go. 400 `FAILED_PRECONDITION` = the exit IP, switch server. 403 = the
account. 429 = quota.

---

## 2. Traps that cost real time tonight — do not rediscover them

| trap | what happens | what to do |
|---|---|---|
| **Gemma returns HTTP 500 on ~1 call in 3** | a hand-rolled retry loses whole runs | use `LLMClient(chain=buckets(provider))` — four gemma buckets across both keys. `score_answers.py` and `draft_queries.py` both do this |
| **flash-lite's 500/day is spent** | every rerank call stalls 70s then fails | `export GOOGLE_API_KEY="$GOOGLE_API_KEY_2"` — Google bills per project per model, so the second account is a second quota |
| **`grep` in a pipeline buffers** | a background log shows nothing for 10 minutes, then the process dies and the output is LOST | write the log UNFILTERED (`> log 2>&1`), filter when reading |
| **`ps -W \| grep -c score_answers`** | always 0 — `ps` shows the interpreter path, not the script | `grep -c 'labpilot/.venv/Scripts/python'` |
| **`pkill` does not exist** here | the "stop" is a silent no-op and TWO loops then write one log | `ps -W`, then `kill -9 <pid>` |
| **pre-commit stashes unstaged files** | an unstaged edit was silently lost once | stage everything before committing, and `grep` the file afterwards to confirm the change survived |
| **the VPN link is the bottleneck** | three jobs at once → SSL handshake timeouts | run at most two API-hitting jobs together; they now retry, but it is slow |

---

## 3. WHAT IS INCOMPLETE — do not read these as results

- **`artifacts/slice8v2/answers/` and `.logs/answers.log`** — the top-N run on
  13 whole corpora was **interrupted by a network collapse**. Partial. Re-run
  it from scratch.
- **`.logs/phase7b.log`** — merged vs per-side on two unrelated corpora never
  finished. Only the `quora` half exists (50% of slots, identical score).
- **`.logs/phase5b.log`, the `--no-header` section** — died when flash-lite's
  quota ran out. No numbers.

Everything in `.logs/results/*.json` IS complete and trustworthy.

---

## 4. RUN THESE, in this order

### 4.1 Finish the top-N measurement  *(the one the user rejected and I rebuilt)*

```bash
PYTHONPATH=. .venv/Scripts/python.exe -u scripts/score_answers.py \
  websocket quora docx log cobra requests notebooks papers docs jq geo gson zod \
  --n=5,10,20,30,50 --model=gemma31 > .logs/answers.log 2>&1 &
```

~65 calls on Gemma's 57,600/day. **Whole corpora, never slices** — the user
rejected slicing and was right: `geo[:50]` is the first 7% of a library with
broken references, and nobody uploads that.

**What it answers:** `N` is a different thing at each corpus size — 50 chunks
is 50% of a 100-chunk artifact and 5% of a 1,000-chunk one. Across 13 natural
sizes:

- if the best `N` is **flat** → it is about the COUNT
- if it **tracks a percentage** → it is about COVERAGE, and 50 is far too few
  on a repository

**The constraint that must survive the answer:** a prompt over **16,000 input
tokens** disqualifies Gemma (14,400 calls/day) and leaves only Gemini Flash
(20/day). 20 chunks fit every tier; 68 do not.

### 4.2 The `SEARCH_LIMIT` window sweep — still rests on ONE corpus

```bash
export GOOGLE_API_KEY="$GOOGLE_API_KEY_2"
for c in geo jq cobra papers; do for w in 10 20 30 100; do
  PYTHONPATH=. .venv/Scripts/python.exe -u scripts/score_rerank.py \
    "$c" codestral --flashlite --window=$w
done; done
```

Everything this run measured used window 50. The first run's sweep was `geo`
alone and found 50 best for MRR/`r@1`, 100 best for `r@10`.

### 4.3 `gemini-embedding-2` on five more corpora

```bash
export GOOGLE_API_KEY="$GOOGLE_API_KEY_2"     # its own unused 1,000/day
for c in websocket docx log cobra notebooks; do
  PYTHONPATH=. .venv/Scripts/python.exe -u scripts/warm_embeddings.py "$c" gemini-embedding-2
  PYTHONPATH=. .venv/Scripts/python.exe -u scripts/score_hybrid.py "$c" google2
done
```

884 texts, fits one day. Its "worst of five" ranking rests on **3 corpora, 2
of them saturated** — too thin, and the user was right to challenge it. This
also directly tests the new Google-first routing, since those are exactly the
corpora it now serves.

### 4.4 Merged vs per-side, two UNRELATED corpora

```bash
export GOOGLE_API_KEY="$GOOGLE_API_KEY_2"
PYTHONPATH=. .venv/Scripts/python.exe -u scripts/bench_merged.py cobra+log papers+notebooks
```

The question is **not** which scores higher. It is **how often merged starves
a side**, because that is the failure per-side exists to make impossible.

### 4.5 Cohere and `rerank-3` as rerankers

```bash
for c in geo jq papers; do
  PYTHONPATH=. .venv/Scripts/python.exe -u scripts/score_rerank.py "$c" codestral --cohere
done
```

Cohere is the chain PRIMARY and is scored on one corpus. **1,000 calls a
MONTH** shared with embedding — 60 calls is 6%. `--voyage3` is free-ish but
capped at ~30 documents on a card-free account.

### 4.6 End-to-end time

```bash
PYTHONPATH=. .venv/Scripts/python.exe -u scripts/bench_end_to_end.py
```

`WARN_MINUTES = 2.0` is still a guess and `services.py` says so.

### 4.7 Fold everything into CLAUDE.md  *(the last step)*

None of the corrections are in CLAUDE.md yet. See §6.

---

## 5. Reading the numbers

```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --metric=MRR
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --metric=r@50
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --rerank
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --by=format
PYTHONPATH=. .venv/Scripts/python.exe scripts/aggregate.py --by=splitter
PYTHONPATH=. .venv/Scripts/python.exe scripts/validate_fixture.py --all
```

**The rules these obey, from CLAUDE.md:**

1. Judge a method by **how many independent ways** it was shown better, never
   by its best single number.
2. **Report headroom beside every metric.** 5 of 13 corpora are saturated at
   `r@50 = 1.000` and cannot show a gain. Slice 5 decided fusion on two of
   those; slice 6 decided the gate on one.
3. **Name the corpus AND the embedder** beside every number.
4. A tolerance must match what the fixture can resolve — on 20 queries, one
   query moving one place is **0.025 MRR**, so a 0.006 "loss" is noise. Using
   a zero tolerance is how I got the wRRF verdict wrong tonight.

---

## 6. What CLAUDE.md still says that is now WRONG

The last job. Every one of these needs updating with the evidence:

| CLAUDE.md says | measured |
|---|---|
| `SKIP_MARGIN = None` "confirmed three times" | **`0.05`** — beats always-rerank, loses on 2 of 13, skips 18% of rerank calls |
| "not one fusion setting improved `r@50`" | 4 of 13 improve; 9 have no room. `k` and `w` depend on corpus SIZE |
| slice 6's routing signal (`structure` −0.534) | does **not** reproduce — `structure` has the HIGHEST mean (+0.148) of five kinds |
| "below ~1,000 rows the planner refuses the index" | **~700**, measured on 12 artifacts |
| "Go chunks are big" | **having no AST splitter** makes chunks big — 5 languages, 430–481 tokens |
| `o = 50` overlap | `o = 25` is better; `o = 100` is the worst of four |
| `VECTOR_TOP_N = 25`, `RERANK_TOP_N = 10` "unmeasured" | 10 is too small. The rest waits on §4.1 |
| `MIGRATION` is one strength order | **a small corpus now goes to Google first** — `SMALL_CORPUS_CHUNKS = 500` |
| BGE's tokenizer ratio "2.36x" | **1.12–1.45x** — 2.36 compared BGE to codestral, a different denominator |

Also still **unfixed production defects**, both named in the first run and
still true:

- `MAX_BATCH_SIZE = 96` is a **Mistral** constant with a global name, so a
  Google embedder fails on its first batch for any corpus averaging over
  ~312 tokens/chunk
- `embedding_minutes()` counts HTTP calls where Google counts **texts**, and
  models no daily request budget at all

---

## 7. The zoo

13 corpora, 9 languages and formats, 286 queries, **nothing committed** —
each `queries.json` names its repo, commit, licence and env var.

```
websocket  78 Go      quora     82 Py+MD   docx     85 Word
log       146 Rust    cobra    193 Go      requests 335 Py
notebooks 382 ipynb   papers   404 PDF     docs     463 MD
jq        693 C       geo      729 Go      gson     750 Java
zod      1160 TS
```

Fetch them with `git clone --depth 1` at the commit each fixture names, then
point `.corpora/env.sh` at the checkouts. `scripts/validate_fixture.py --all`
proves they are intact.

**Caches are paid-for data, not results.** `.cache/hybrid/` holds the vectors;
they were validated this run to `|1 - cos| = 3e-10`. Both the reader and the
writer now refuse a cache whose vector count disagrees with the corpus.

---

## 8. Suite state

```
752 passed, 4 skipped   (tests/unit + tests/api)   ruff clean both ways
```

Smoke tests were **not** run — they spend live quota and need the ISP probe
first.
