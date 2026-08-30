# Where the sample files came from

Every binary fixture in `data/samples/` is a **third-party document downloaded
from a public source**, kept so the loader tests run on real files rather than
on files we wrote ourselves. That distinction matters: a hand-built file proves
the *mechanism*, never the *library*.

None of these are ours. Attribution below.

---

## `docx/`

| file | source | licence |
|---|---|---|
| `ddos_ensemble.docx` | Zenodo record [18269425](https://zenodo.org/records/18269425) — *An Approach to Detect DDoS Attacks in Application Layer using Machine Learning* | **CC-BY-4.0** |

CC-BY-4.0 permits redistribution with attribution, which this file provides.

**Why this one.** Chosen from six candidate Word papers by measurement, not by
taste. It carries the most implementable method detail — named classifiers,
a stated train/test split, a Kaggle dataset, and 62 decimal result numbers —
and network security is a genuinely different domain from `quora_siamese`.
It is intended to become side A of the **second sample pair** that slice 8
needs.

---

## `pdf/`

All three are arXiv preprints, downloaded from `arxiv.org/pdf/<id>`. They are
test fixtures only, never redistributed as a publication.

| file | arXiv id | paper | why it is here |
|---|---|---|---|
| `one_column.pdf` | [1706.03762](https://arxiv.org/abs/1706.03762) | *Attention Is All You Need* | the **one-column** case |
| `two_column.pdf` | [1512.03385](https://arxiv.org/abs/1512.03385) | *Deep Residual Learning for Image Recognition* | the **two-column** case, the one the loader had to get right |
| `type3_garbled.pdf` | [0704.0001](https://arxiv.org/abs/0704.0001) | *Calculation of prompt diphoton production cross sections at Tevatron and LHC energies* | **Type3 fonts** — extracts as glyph names and must be REFUSED |

**arXiv licences vary per submission** — most are arXiv's non-exclusive
distribution licence rather than a Creative Commons one. Check the abstract page
before reusing any of these outside this repository.

---

## `quora_siamese/`

Not third-party. `B_train.py` is the user's own research code, flattened from
their Quora Question Pairs notebooks. `A_paper.md` and `EXPECTED.md` were
written for this project.

---

## Rules for adding a fixture

1. **Record the source and licence here in the same commit.** A binary with no
   provenance cannot be audited later, and git keeps it forever.
2. **Prefer a real file over one we generate.** Generated files prove only that
   our own parser agrees with our own writer.
3. **Generate, do not download, when the case is trivial to construct** — a
   scanned PDF is "pages with no text operators", so the test builds one and no
   binary is committed.
4. **Keep them small.** These are stored uncompressed in git history forever.
