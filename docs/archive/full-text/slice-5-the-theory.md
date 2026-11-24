# Full text: Slice 5 — the theory, recorded 2026-09-06

[Docs home](../../README.md)

## Slice 5 — the theory, recorded 2026-09-06

*Session 18 wrote no source on purpose. The keyword half of hybrid search was
**probed against the real database first**, because slice 5's whole plan rested
on one sentence that had been written and never run.*


### The claim that was an assumption, and it is TRUE

> *"A keyword search matches `clip` and `norm` immediately, because they are
> inside the identifier."*

Measured. Postgres labels `_` a **blank** — the same token class as a space —
so an identifier really does split:

```
CLIP_NORM = 1.5   ->   asciiword 'CLIP' · blank '_' · asciiword 'NORM' · float '1.5'
                  ->   tsvector: 'clip':1 'norm':2 '1.5':3
```

Stemming then closes the gap from the other side: the query word `clipped`
stems to `clip`. **Both steps are needed.** Without the split, `clip_norm`
never meets `clip`; without stemming, `clipped` never does.

**A dot is NOT a blank**, and that is the limit nobody had recorded:

```
torch.nn.utils.clip_grad_norm_(params, 1.5)
  ->  'torch.nn.utils.clip' · 'grad' · 'norm' · 'param' · '1.5'
```

The parser reads a dotted path as a **host name** and keeps it whole. So a
query about a dotted call path does not decompose the way an underscore does.


### The operator matters more than the ranker — 0 of 17, then 14 of 17

The first probe scored **0 of 17**. Not one query matched a single chunk, which
reads exactly like *"keyword search does not work on code"*. It was the probe.

`plainto_tsquery` joins terms with **`&`**, so one chunk must hold **every** word
of the sentence — which a 500-token chunk essentially never does. Converting the
lexemes to an **OR** query (`tsvector_to_array` -> `array_to_string(..., ' | ')`)
changed nothing else:

```
AND   recall@5 0.000
OR    recall@5 0.824
```

> **A zero result is a result about your instrument until you prove otherwise.**
> Same family as *"prove the mutation actually changed behaviour"*.


### The measurement — 82 chunks of `B_train.py`, the same 17 graded queries

| | recall@1 | recall@5 | recall@10 | MRR | **`D2`** |
|---|---|---|---|---|---|
| **cosine** (codestral) | **0.412** | **0.941** | 0.941 | **0.608** | **46** |
| `ts_rank` (OR) | 0.235 | 0.824 | 0.941 | 0.458 | **4** |
| `ts_rank_cd` (OR) | 0.353 | 0.765 | 0.941 | 0.486 | 5 |

**Keyword search alone is WORSE, and that is not the point.** The two methods
fail on *different* queries, which is the only condition under which fusing them
can pay:

- **cosine fails `D2`** — rank 46. The answer is the constant `CLIP_NORM = 1.5`.
- **keyword fails `D14`** — 7 chunks matched and the target was not among them.
  The query is *"the vocabulary keeps only the most frequent words…"*: meaning,
  with no shared identifier.

**And both methods make the same mistake at rank 1 on `D2`.** Each returns
`_backprop_with_scaler`, the code that *calls* `clip_grad_norm_` — because that
name also splits into `clip` + `norm`. Keyword search cannot tell the constant
from the call; it only sees words. It simply ranks the constant 4th instead of
46th.


### Postgres has NO BM25, and the reason is structural

CLAUDE.md's slice-5 line said *"BM25 catches identifier queries like `D2`"*. The
**conclusion** survived; the **named mechanism** did not.

```
ts_rank(tsvector, tsquery) -> float4
```

The function receives **one document**. No corpus, so it cannot know `N` or
`n_t`, so **IDF is impossible by construction**. `ts_rank` uses term frequency
within the single document plus the A/B/C/D position weights; length
normalization exists but is an optional argument, off by default. `ts_rank_cd`
adds only **cover density** — how close the query terms sit to each other.

$$
\text{BM25}(q,d) = \sum_{t \in q} \text{IDF}(t)\cdot
\frac{f(t,d)\,(k_1+1)}{f(t,d) + k_1\left(1-b+b\,\frac{|d|}{L}\right)}
\qquad
\text{IDF}(t) = \ln\frac{N-n_t+0.5}{n_t+0.5} + 1
$$

`f(t,d)` occurrences of term `t` in document `d` · `|d|` its length · `L` the
average length · `N` documents · `n_t` documents holding `t` · `k_1 ≈ 1.2`
saturation · `b ≈ 0.75` length normalization.

**The cost of having no IDF is already visible.** Query `D6` matched **73 of
82** chunks, because an OR over common words matches nearly everything. With
IDF the common terms would be almost free and the rare ones would decide. It
still ranked `D6` first here — but that is an 82-chunk fixture being kind, not
a property to rely on at 10,000 chunks.


### BM25 BY HAND is now a scheduled experiment — the user's call, 2026-09-06

**Not an extension.** `pg_search` (ParadeDB), `pg_textsearch` and
`VectorChord-BM25` all add real BM25 to Postgres and **Supabase offers none of
them** — ParadeDB's own Supabase page is an external-instance story, not a
managed extension. Verified from the providers' own pages, per the sources rule.

**Not in SQL either.** ParadeDB state plainly that the three parts of BM25 *can*
be computed from what Postgres already keeps, and that doing so is *"very
convoluted and very slow"*.

**So: compute it in Python.** One artifact is ~1,000–10,000 chunks, `N` and
`n_t` are one pass over the stored tsvectors, and nothing has to be maintained
in the schema to try it.

**Slice 5 therefore measures THREE keyword rankers, not one:**

| # | Ranker | Where it runs |
|---|---|---|
| 1 | `ts_rank` | Postgres, already exists |
| 2 | `ts_rank_cd` | Postgres, already exists |
| 3 | **BM25, written by hand** | **Python, over the same tsvectors** |


### The fixture is SATURATED, so it may REJECT and may not CONFIRM — 2026-09-07

*The user challenged the rule above the same day it was written, and was right.
The correction matters more than the rule it replaces.*

**The instrument is nearly full.** Cosine already scores 16 of 17 on recall@5.
Over 17 queries that metric can only take three values from here:

```
recall@5   0.882   0.941 (today)   1.000
           nothing exists in between
```

One query is **5.9 points**. Most real differences between retrieval methods are
smaller than that. So a hybrid ranking that is genuinely a little better would
report **"no change"**, and rule 1 as first written would then delete working
code on the strength of a measurement that could not have detected the gain.

**And the queries carry the leakage this file already warns about elsewhere.**
The Slice 8 section says the 17 are *"enough to pick a default and not enough to
pick a policy"* — 17 queries, one author, one Python file. Slice 5 inherits every
word of that. Worse: `D2` was already the known hard case, and `D2` is now the
motivating example for this whole slice. **The fix is being scored on the example
that produced the idea.**

**What the fixture CAN still do**, and this is not nothing:

- **Catch a large regression.** A drop to ~10 of 17 is real news at any sample size.
- **Confirm one large single fact.** `D2` moving from place 46 to place 4 does not
  need statistics; it is a 42-place move on a known query.

**The corrected decision rules:**

1. **This fixture may REJECT, never CONFIRM.** If the mix clearly hurts, drop it.
   If it ties or helps a little, **keep the code** and let slice 8 decide.
   Deleting is the hard thing to undo, so the weak instrument must not be the
   thing that does it.
2. **Rank on MRR and on the PLACE of the correct chunk, not on recall@5.** Those
   move in small steps, so they can see a difference recall@5 cannot resolve.
   Report recall@5 alongside; do not decide on it.
3. **Write a second query set before slice 8** — more queries, a second corpus,
   another language. Queries cost no money and no quota, so this is the cheapest
   improvement available to the whole of Step 1.
4. **BM25 ships only if it clearly beats the better of `ts_rank` / `ts_rank_cd`.**
   It needs term counts we do not store today, so it is not free. A tie is a loss.
5. **Measure the mix FIRST, BM25 second.** Building BM25 before knowing whether
   the fused result helps at all would be a day spent on a channel we may drop.
6. **Re-check `D2` on the embedder that actually wins slice 8.**
   `gemini-embedding-001` already ranks `D2` **3rd** where codestral ranks it
   46th. A better embedder weakens part of the argument for this whole slice, so
   the motivating case must be re-run after any model change.

> **A saturated test cannot measure an improvement.** Before trusting a number
> to make a keep-or-delete decision, ask how much room it has left to move. Ours
> had one query.
