# EXPECTED — the answer key for the `quora_siamese` sample pair

**This file is not input to LabPilot.** It never gets ingested, chunked or
embedded. It exists so that a wrong output is obvious immediately, and so the
same pair can later seed a fine-tuning example.

- **Side A** — `A_paper.md`, the reference. A method paper written for this
  fixture. Its numbers in §6 and §7 are invented, as any fictional paper's are.
- **Side B** — `B_train.py`, the implementation. Flattened from the real
  notebooks in `research-notebooks/Quora Questions Pairs/research/`
  (`02-train.ipynb` + `model_architecture.py`). **The code is real. Every
  divergence below was found by reading it, not planted.** The `DATA`, `MODEL`
  and `RUN SUMMARY` blocks in the module docstring are **also real** — they are
  transcribed from the notebook's stored outputs (MLflow run
  `LSTM_attention-MultiHead-Bahdanau-v10`). Nothing on side B is invented.

## Size — retrieval is genuinely required

| | est. tokens |
|---|---|
| `A_paper.md` | ~3,800 |
| `B_train.py` | ~16,200 |
| **total** | **~20,000** |

`INPUT_BUDGET` is 20,000 tokens *including* instructions and the question. The
pair alone fills it, so stuffing is impossible and retrieval must work. This is
deliberate — see *Stuff, do not retrieve* in CLAUDE.md.

## What the chunker must survive

| Path | Where it is exercised |
|---|---|
| Markdown header split | 20 sections in `A_paper.md` |
| Section over the 510 cap → second-pass split + repeated header | `### 4.3 Attention pooling`, ~656 tokens |
| Section under the ~30 minimum → **merge**, never store alone | `# title`, `## 4. Method`, `## 5. Experimental Setup` |
| Python AST split | `B_train.py` parses clean |
| AST unit over the 510 cap → split per method, then per block | **11 units**, largest is `class Trainer` at ~5,300 tokens |
| Training loop must stay whole | `Trainer.fit`, lines 1172–1300 |

---

## The divergences

### Type 1 — stated and wrong (row reading, `verify`)

| # | Paper says | Code does | Where |
|---|---|---|---|
| 1 | attention returns $\sum_i \alpha_i h_i$, a weighted sum of the **encoder hidden states**; §4.3 states explicitly that the projection is for scoring only | pools `masked_proj`, the **projected** features. The code's own comment admits it | `B_train.py:584-586` |
| 2 | gradient clipping at global norm **1.0** (§5.2) | `CLIP_NORM = 1.5` | `B_train.py:221` |
| 3 | label smoothing **ε = 0.1** (§4.5) | `LABEL_SMOOTHING = 0.05` | `B_train.py:188` |
| 4 | weight decay **0.01** (§5.2) | `WEIGHT_DECAY = 1e-3` | `B_train.py:240` |
| 5 | embeddings unfrozen from **epoch 3**, i.e. after 2 frozen epochs (§5.2) | `UNFREEZE_EPOCH = 3` with a 0-based loop, so it fires after **3** frozen epochs | `B_train.py:239`, `1190-1194` |

**#1 is the flagship.** It is architectural, it is subtle, and the paper's §7
ablation prices it at −1.4 F1. A correct report must name it and cite the line.

### Type 2 — stated and absent (row reading, `verify`)

| # | Paper says | Code | Where to look |
|---|---|---|---|
| 6 | positive class weighted by $w_+ = N_-/N_+ \approx 1.71$ (§4.5) | `pos_class_weight()` is **defined and never called**. The criterion is plain `BCEWithLogitsLoss` inside `BCEWithLabelSmoothing` | defined `B_train.py:544`, criterion built `B_train.py:1365` |
| 7 | linear warmup over 2 epochs, then cosine decay to 1e-6 (§5.2) | `ReduceLROnPlateau`. **No warmup anywhere** | `B_train.py:241` |
| 8 | three splits — train / dev / **test**, and the test split is never used for tuning (§5.1) | one `train_test_split` at 0.9. There is **no test set** | `B_train.py:238`, `1315-1321` |
| 9 | threshold chosen once on **dev**, applied unchanged to **test** (§5.4) | threshold re-tuned on the validation set inside `evaluate()`, then the same set's metrics recomputed at that threshold | `B_train.py:1129-1130` |
| 10 | every number is the mean of **3 seeds**, deterministic kernels on (§5.3) | one seed, `IS_DETERMINISTIC = False`, `cudnn.benchmark = True` | `B_train.py:62`, `299` |
| 10b | the train-to-test F1 gap is **2.1 points**, and the dropout rates are therefore sufficient (§6) | the real gap is **12.1 points** — train F1 0.9439 against val F1 0.8226 at epoch 15. The paper even names the cause: it appears once the embedding matrix becomes trainable, which is exactly what `UNFREEZE_EPOCH` does | run summary in the module docstring |

**#9 is the one a weak system will miss**, because nothing is named "wrong" —
the code simply measures on the data it tuned on.

### Type 3 — present but unstated (column reading, `find_missing`)

The paper never mentions any of these. They exist only in the code.

| # | The code does | Where |
|---|---|---|
| 11 | **masks every NLTK stopword out of the attention** — `not`, `what`, `how`, `why`, `is`, `from`, `to` can never be attended to | `_build_stop_mask`, `B_train.py:433-453` **and** `_encode`, `B_train.py:661-662` |
| 12 | also masks punctuation and `<UNK>`, so out-of-vocabulary tokens are invisible to attention | same, `B_train.py:435-453` |
| 13 | appends **cosine similarity** as a 3073rd interaction feature; the paper's $r$ has only $4d$ dimensions | `QuoraSiameseClassifier.forward` |
| 14 | vocabulary capped at 20,000 with a whitespace tokenizer, so OOV rate is non-trivial and every OOV is then masked | `B_train.py:132` |
| 15 | drops rows whose questions are empty *after* the punctuation-spacing regex | `QuoraPreproccesor.preprocess_df` |
| 16 | `emb_norm`, `lstm_norm`, `attn_norm` are constructed but every layer-norm flag is `False` — three dead modules | `QuoraSiameseClassifier.__init__` |
| 17 | `"requires_grad": False` is passed as an **optimizer param-group key**, where it does nothing. Freezing actually happens via `weight.requires_grad` | `B_train.py:1377` |

**#11 is the scattered fact.** The stopword list is built in the tokenizer and
applied in the model — two locations, ~230 lines apart. **One retrieved chunk
cannot explain it.** This is the case that proves neighbour expansion and
multi-query retrieval matter.

### Type 4 — a latent bug neither side mentions

18. When **every** token of a question is a stopword — `"what is it ?"`, which
    is a real Quora row shape — the mask is all zeros. Every score becomes
    `MASK_FILL_NUM = -1e10`, softmax over a constant vector returns a **uniform**
    distribution, and the context vector becomes the mean of `proj * 0`, i.e.
    the zero vector. The question silently encodes to nothing.
    `B_train.py:204`, `584-586`, `661-662`.

    This is findable with **one** artifact — it is wrong against general
    programming knowledge, not against the paper. It belongs to `find_bugs`,
    not to `verify`.

---

## The expected causal explanation

This is the paragraph `explain_divergence` has to produce.

| | F1 | measured on |
|---|---|---|
| paper, §6 | **0.851** | held-out **test** split, threshold fixed from dev |
| code, best checkpoint | **0.8262** | **validation** split, threshold re-tuned **on that same split** |

**The first thing a correct report must say is that these two numbers are not
comparable.** They are computed on different splits under different protocols.
Subtracting them to get "2.5 points behind" is the wrong move, and it is the
move a naive system will make.

Pushing the code's number **down** — four defects, with the paper's own §7
ablation cost beside each:

1. **Stopword masking (#11) is the dominant cause, −4.1 F1.** Duplicate
   detection turns on function words: *how* against *why*, *is* against *is
   not*. Two questions differing only by a negation become identical to the
   attention layer. This is the largest single row in the paper's ablation
   table, and the code does it silently.
2. **No positive-class weighting (#6), −1.9 F1.** On a 63/37 split this costs
   recall on the minority duplicate class.
3. **Pooling projected features (#1), −1.4 F1.**
4. **No warmup (#7), −0.8 F1.**

Pushing the code's number **up**:

5. **The threshold is tuned on the split it is reported on (#9), and there is no
   test set (#8).** The paper prices this optical gain at about +1.5 F1. The
   run summary proves it is real rather than theoretical: the "optimal"
   threshold swings 0.4358 → 0.3970 → 0.4825 → 0.3893 → 0.4631 → 0.5787 across
   six consecutive epochs. A threshold that moves by 0.19 between epochs is
   fitting validation noise, not a property of the model.
6. **The model is heavily overfit (#10b)** — train F1 0.9439 against val F1
   0.8226. Some of the reported validation score comes from a model that has
   memorised training pairs, and the paper names the mechanism: it appears once
   the embedding matrix becomes trainable, which `UNFREEZE_EPOCH = 3` does.

**The arithmetic does not close, and saying so is part of the correct answer.**
The four defects predict roughly −8 F1 if the ablations composed additively, yet
the observed gap is about 2.5. Three honest readings, and a good report offers
them rather than pretending to certainty:

- ablation effects do not add — they overlap, and the paper never claims they do;
- the code's number is inflated by #9 and #8, so the true gap is wider than 2.5;
- the code has advantages the paper does not: an extra cosine-similarity
  interaction feature (#13), and embeddings that are unfrozen and trained.

### The next experiment to propose

**Remove the stopword mask** — one line, `B_train.py:661-662` — and retrain with
nothing else changed. It is the cheapest single edit, it has the largest
predicted effect, and it is the only one that tests a *hypothesis about the
model* rather than a hyperparameter value.

Two supporting changes, both needed before any number is trustworthy: carve out
a real held-out test split so the metric becomes comparable at all, and fix the
threshold once on the dev split instead of re-selecting it every epoch.

---

## How to grade a slice 3 run

The dumb selector is **expected to fail**. Watching it fail is the point of the
slice. Grade it against this:

| Signal | Verdict |
|---|---|
| Returns `TrainConfig` scheduler constants for a question about the learning rate schedule | the distractors are working — `SCHEDULER_T_0`, `SCHEDULER_PCT_START`, `SCHEDULER_DIV_FACTOR` are all configured but **dead**, only `ReduceLROnPlateau` is live |
| Returns `MLflowTracker` chunks for anything | pure noise retrieved — this is the failure Step 1 must fix |
| Finds #2, #3, #4 (plain value mismatches) | the easy tier — a keyword match would find these |
| Finds #1 or #6 | good retrieval — needs the right chunk, not the right keyword |
| Finds #11 | **needs two chunks from two classes.** A single-shot retriever should not manage it |
| Claims a finding with no citable line | the citation rule caught a hallucination — reject the output |
