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

---

## `requests_http/`

**No third-party file is committed here.** The corpus is the `psf/requests`
library, which is fetched on demand; only our own `queries.json` lives in the
repository. Fetch it at the commit the query file names, or every line number
in the ground truth is wrong:

```
git clone --depth 1 https://github.com/psf/requests <dir>
```

| what | value |
|---|---|
| repository | https://github.com/psf/requests |
| commit | `dae7ef6` |
| files used | `src/requests/*.py` -- 19 files, 6,394 lines, 335 chunks |
| licence | Apache-2.0 |

**Why this corpus.** Slice 5 needed a second fixture that was real, was written
by somebody else, and was **not** about machine learning -- so that a result
measured on `quora_siamese` could be shown to hold, or not, somewhere else. It
also gave the first multi-file corpus, which exposed that a query file needs a
`file` field: line 186 exists in most of the 19 files.

## `golang_geo/queries.json` — the third retrieval fixture

- **Queries and ground truth: ours.** Written 2026-09-16 for slice 8, from
  reading the corpus. No source text is copied into them.
- **The corpus is NOT committed.** `golang/geo` at commit `b200a11`,
  https://github.com/golang/geo, **BSD-3-Clause**. It is third-party source,
  so the provenance rule keeps it out of the repository: clone it with
  `--depth 1` and point `LABPILOT_GEO_SRC` at the checkout.
- **Why this corpus:** the first fixture that is neither Python nor machine
  learning, the first measured through `split_recursive`, and the first whose
  vector `r@50` is not saturated.


## The slice 8 corpus zoo — ten more fixtures, 2026-09-16

Slice 8's first run measured three corpora, two of which had been used before.
These ten were added so a retrieval claim can be made across languages and
formats instead of across one language and one domain.

**Queries and ground truth are OURS** for every corpus below. They are drafted
by the gemma chain against the real chunk text, then machine-validated for
resolvability, breadth, duplication and identifier leakage, and spot-checked by
hand. `scripts/draft_queries.py` and `scripts/validate_fixture.py` carry the
rules; the drafter is recorded in each fixture's `drafted_by`.

**No corpus is committed.** Each `queries.json` names its repository, its
commit and its licence, and an environment variable pointing at a checkout —
the same rule `geo` and `requests` already followed.

| fixture | source | licence |
|---|---|---|
| `go_cobra` | github.com/spf13/cobra @ `adbc881` | Apache-2.0 |
| `go_websocket` | github.com/gorilla/websocket @ `e064f32` | BSD-3-Clause |
| `rust_log` | github.com/rust-lang/log @ `8034743` | MIT OR Apache-2.0 |
| `c_jq` | github.com/jqlang/jq @ `1b4109b` | MIT |
| `java_gson` | github.com/google/gson @ `698ba9e` | Apache-2.0 |
| `ts_zod` | github.com/colinhacks/zod @ `59bbc03` | MIT |
| `md_docs` | the Markdown of six of the repositories above | each project's own |
| `pdf_papers` | eight arXiv papers, fetched | each paper's own arXiv licence |
| `ipynb_notebooks` | the user's own notebooks, local | personal, never committed |
| `docx_reports` | the user's own Word documents, local | personal, never committed |

**Why these.** Five of them have no AST splitter, so `split_recursive` is
measured five more times rather than once. Three of them are document formats
whose loader path had never been scored at all. Two are above 1,000 chunks and
two are under 150, so "it works at our size" stops meaning "it works at the one
size we tried".


## The v3 Python zoo — ten more fixtures, 2026-09-19

Slice 8 was run a third time because the zoo did not match the product.
LabPilot is a **Python and machine-learning** tool, and the v2 zoo was 3 of 13
Python — so three shipped decisions had no Python behind them at all. These ten
take the zoo to **20 corpora, 10 of them Python**.

**Queries and ground truth are OURS** for every corpus below, and each fixture
records its own `drafted_by`. Seven were drafted by `gemma-4-31b-it` against the
real chunk text and then machine-validated by `scripts/validate_fixture.py`;
**three are hand-written with no model involved**, and exist as the control that
says whether a drafted fixture is as good as a written one.

**No corpus is committed.** Every `queries.json` names its repository, its
commit, its licence and the environment variable pointing at a checkout.

| fixture | source | licence | drafted by |
|---|---|---|---|
| `py_pydantic` | github.com/pydantic/pydantic @ `915896d` | MIT | `gemma-4-31b-it` |
| `py_pydantic_hand` | the same corpus and commit | MIT | **hand-written** |
| `py_pytest` | github.com/pytest-dev/pytest @ `6a0de9b` | MIT | `gemma-4-31b-it` |
| `py_pytest_hand` | the same corpus and commit | MIT | **hand-written** |
| `py_click` | github.com/pallets/click @ `6aabf09` | BSD-3-Clause | `gemma-4-31b-it` |
| `py_lung` | the user's own application, local | personal, never committed | `gemma-4-31b-it` |
| `py_lung_hand` | the same corpus | personal, never committed | **hand-written** |
| `py_smsspam` | the user's own application, local | personal, never committed | `gemma-4-31b-it` |
| `py_disaster` | the user's own application, local | personal, never committed | `gemma-4-31b-it` |
| `ipynb_titanic` | the user's own research notebook, local | personal, never committed | `gemma-4-31b-it` |

**Why these.** Four are the user's own work, which is the real target and had
never been measured. Three pair a drafted fixture with a hand-written one over
the *identical* corpus, so "are generated queries trustworthy?" becomes a
measurement instead of an argument. `py_pytest` and `py_pydantic` are both above
9,000 chunks, which is the size the product actually targets and the zoo had
never reached.

**A note on the four personal corpora.** They are named here and are **not** in
the repository, and they never can be. So those four fixtures are reproducible
only on this machine; the six public ones are reproducible anywhere.
