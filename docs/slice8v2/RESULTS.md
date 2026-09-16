# SLICE 8, SECOND RUN — the measurement, and what it decides

Run 2026-09-16/17. Exit `80.240.20.89`, **AS20473 The Constant Company**
(Vultr, Frankfurt); `gemini-3.5-flash-lite:generateContent` answered **200**,
so the probe decided it and the ISP name did not.

Every number here is reproducible from the repository: `score_hybrid.py`,
`score_rerank.py`, `sweep_fusion.py`, `sweep_chunking.py`, `score_topn.py`,
`bench_index.py`, `bench_merged.py`, `aggregate.py`, and thirteen fixtures.
Findings with their evidence are in `FINDINGS.md`; the coverage checklist is
`MEASUREMENTS.md`.

---

## 0. Why this run exists

The first run (`docs/slice8/`) measured **three corpora, two of which had
already been used**, and left `VECTOR_TOP_N`, `RERANK_TOP_N`, the wRRF
parameters, the search window, merged-vs-per-side and the BM25 knobs open.
Every headline therefore rested on one new fixture.

**This run is thirteen corpora, nine languages and formats, 286 queries** — and
it overturns or corrects **seven** recorded conclusions, five of which were
"confirmed" by an earlier run on one or two corpora.

| | first run | this run |
|---|---|---|
| corpora | 3 (2 reused) | **13** |
| languages / formats | Python, Go | **Python, Go, Rust, C, Java, TypeScript, PDF, notebook, Markdown, Word** |
| queries | 107 | **286** |
| corpora with headroom | 1 | **8** |

---

## 1. The corpus zoo

| corpus | language / format | splitter | chunks | queries | vector `r@50` |
|---|---|---|---|---|---|
| websocket | Go | recursive | 78 | 15 | 1.000 **saturated** |
| quora | Python + MD | AST | 82 | 17 | 1.000 **saturated** |
| docx | Word | recursive | 85 | 12 | 1.000 **saturated** |
| log | Rust | recursive | 146 | 20 | 1.000 **saturated** |
| cobra | Go | recursive | 193 | 20 | 0.950 |
| requests | Python | AST | 335 | 45 | 0.978 |
| notebooks | Jupyter | cells | 382 | 20 | 1.000 **saturated** |
| papers | PDF | pages | 404 | 20 | 0.950 |
| docs | Markdown | headers | 463 | 19 | 1.000 **saturated** |
| jq | C | recursive | 693 | 20 | 0.900 |
| geo | Go | recursive | 729 | 45 | 0.867 |
| gson | Java | recursive | 750 | 13 | 0.923 |
| zod | TypeScript | recursive | 1,160 | 20 | 1.000 **saturated** |

**Five of thirteen are saturated and cannot show a gain.** That is the single
most important row in this document: slice 5 decided fusion on two saturated
corpora, and slice 6 decided the gate on one.

---

## 2. The decisions

### 2.1 Exact search ships — and the crossover is ~700 rows

Twelve artifacts on the real Supabase instance, every plan asserted.

- exact is **linear at 8.8 µs/row**: `0.25 ms` at 18 rows, `12.25 ms` at 1,387
- the planner **refuses the index below ~700 rows** and uses it above
- where it is used it is 6–10× faster and costs **1–13% of recall**
- at `ef_search = 100` the planner **abandons the index at every size**, so the
  recall cannot be bought back
- the index is **43% of total storage** (59 MB of 136 MB)

**Trade at a real artifact: save ~11 ms of a 90–250 second answer, pay 6–13% of
recall.** Exact ships; revisit at ~20,000 chunks in one artifact.

### 2.2 Reranking ships, and the gate ships with it

`gemini-3.5-flash-lite`, window 50, 13 corpora. `r@50` unmoved on every run.

- **helped 10, hurt 3, mean +0.122**
- `correlation(baseline MRR, gain) = -0.584`; **all 7 corpora at or below MRR
  0.646 were helped**
- **`SKIP_MARGIN = 0.05`**, overturning `None`: beats always-rerank on the mean,
  loses on only **2 of 13**, and **skips 18% of rerank calls**

### 2.3 Fusion: `k` and `w` depend on corpus SIZE

- small corpus (≤ ~300 chunks): `r@50` already 1.000, so keyword can only
  disturb → **`k=5 w=0.05–0.15`**
- large corpus (≥ ~400): `r@50` falls → **`k=60–90 w=0.7`** recovers it to 1.000
- best **single** setting if size is unknown: **`k=5 w=0.3`** — never loses
  `r@50` on any of thirteen, four times the MRR gain of the shipped `k=5 w=0.15`

### 2.4 Send MORE chunks, not fewer

The dilution penalty everyone assumes **is not there** between 20 and 100:

```
10 chunks ->  2/19 findings      68 chunks -> 11/19
20 chunks ->  5/19              100 chunks -> 11/19
```

**`VECTOR_TOP_N = 25` and `RERANK_TOP_N = 10` are very likely too small.**

### 2.5 Chunking

- **`s = 500` is vindicated** — best of five sizes pooled, and the curve has the
  shape the dilution argument predicts
- **`o = 50` is not optimal**: `o = 25` is better and `o = 100` is the worst of
  four. More overlap manufactures competing near-duplicates
- **the free context header earns its place**: +0.022 mean MRR over six corpora,
  largest where a chunk is least self-describing (papers +0.098)

---

## 3. What this run corrects

| recorded | by | now |
|---|---|---|
| "not one fusion setting improved `r@50`" | slice 5, 2 saturated corpora | 4 of 13 improve; 9 have no room |
| "every wRRF setting improved `r@50`" | slice 8 v1, 1 corpus | same — it was one corpus |
| "`SKIP_MARGIN = None`, confirmed 3x" | 1–2 corpora each time | **`0.05`**, saves 18% of calls |
| "reranking: not one negative category" | 2 corpora | helped 10, **hurt 3** |
| "`structure` is where reranking collapses" | slice 6, one model | `structure` has the **highest** mean |
| "Go chunks are big" | 1 Go corpus | **having no AST splitter** makes chunks big — 5 languages |
| "below ~1,000 rows the planner refuses the index" | 3 artifacts | **~700**, measured on 12 |

---

## 4. What this run still may NOT conclude

- **Thirteen corpora is not a population.** They are what one person could
  fetch in a day, weighted toward open-source libraries.
- **English only**, and one author for every query.
- **Generation quality rests on ONE fixture**, because `quora_siamese` is the
  only corpus in this project with an answer key.
- **Queries are drafted and machine-validated**, not hand-written. The two
  hand-written fixtures are in the set and behave like the rest, which is
  reassuring and is not proof.
