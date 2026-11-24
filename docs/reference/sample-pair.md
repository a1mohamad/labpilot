# The sample pair quora_siamese

[Docs home](../README.md)

### The sample pair — `quora_siamese`, built 2026-08-14

`data/samples/quora_siamese/` holds three files; **the pair is the measuring instrument for the whole of slice 3** (without a known answer there is no way to tell a working chunker
from a broken one): `A_paper.md` (~3,900 tokens, side A, the reference, **fictional**, written for this fixture) · `B_train.py` (~16,500 tokens, side B, **real code**, flattened from
`research-notebooks/Quora Questions Pairs/research/`) · `EXPECTED.md` (the answer key, **never ingested**).

**Side B is real and side A is not, deliberately.** The code is the user's own (`02-train.ipynb` plus `model_architecture.py` merged into one file, values, comments and flaws
untouched) and its `DATA` / `MODEL` / `RUN SUMMARY` docstring is transcribed from the notebook's stored outputs (MLflow run `LSTM_attention-MultiHead-Bahdanau-v10`); the paper has to
be invented because a real paper never lines up with a reimplementation cleanly enough to place claims that *match*, *contradict*, and that the code never addresses. **Total ≈ 20,400
tokens against `INPUT_BUDGET` of 20,000**: stuffing is impossible by construction, so retrieval must work (the sizing target).

**18 divergences, in the three kinds the similarity matrix reads:** stated and **wrong** (rows, `verify`) 6 — the paper pools `Σ αᵢhᵢ` over hidden states, `B_train.py:601-603` pools
the **projected** features and the code's own comment says so · stated and **absent** (rows, `verify`) 5 — `pos_class_weight()` is defined at `:561` and **never called** ·
**unstated** but present (columns, `find_missing`) 7 — stopword masking, `_build_stop_mask` at `:450` and `_encode` at `:678`. Plus one latent bug findable from a single artifact:
a question of only stopwords masks to all zeros, so softmax over a constant returns uniform weights and the sentence encodes to the zero vector.

**Three properties worth preserving if the pair is ever replaced:** (1) **the scattered fact** — the stopword finding needs two chunks from two classes ~230 lines apart; (2)
**honest distractors** — `TrainConfig` configures four LR schedulers and only `ReduceLROnPlateau` is live, so any "learning rate schedule" query pulls back dead constants (nothing
planted); (3) **the two numbers are not comparable** — paper 0.851 F1 on a clean test split vs code 0.8262 on a validation split whose threshold was tuned on itself; a naive system
subtracts them ("2.5 points behind"), **the correct answer refuses the subtraction** (the per-epoch threshold sequence 0.4358 → 0.3970 → 0.4825 → 0.3893 → 0.4631 → 0.5787 is the
evidence). **The arithmetic deliberately does not close:** the four defects predict ≈ −8 F1 if the paper's ablations composed additively, the observed gap is ≈ 2.5; a good report
offers the three honest readings (ablations overlap; the code's number is inflated; the code has advantages the paper lacks) instead of asserting one.

**Chunker coverage:** the pair exercises every path on purpose — 3 markdown sections under the ~30-token minimum (**merge**), `§4.3` at ~656 tokens (**second-pass split** with
repeated header), 11 AST units over the 510 cap, `class Trainer` (lines 920-1317) at ~5,300 tokens, `Trainer.fit` (lines 1189-1317) as the training loop that must stay whole.
**`data/samples/` is excluded from ruff and pre-commit** (data, not source: `ruff check .` would fail CI on flaws that are the point, and `ruff-format` would move the exact lines
`EXPECTED.md` cites; the exclusion is in both `ruff.toml` and `.pre-commit-config.yaml` and the two must stay in step; ingest still reads the files normally). **A process lesson:**
the first version invented the run summary because the notebook dump extracted cell *source* and skipped cell *outputs*; **when a notebook is the source of truth, read its outputs,
not only its code** — stored outputs are the only record of what actually happened.

