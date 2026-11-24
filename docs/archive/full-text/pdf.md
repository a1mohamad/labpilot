# Full text: `.pdf` — DONE 2026-08-30, measured on 24 real papers

[Docs home](../../README.md)

## `.pdf` — DONE 2026-08-30, measured on 24 real papers

*The theory was written in session 14 and never touched a library. This is what
happened when it did. **480 passed, 28 skipped, 2 xfailed, ruff clean.** All four
new invariants were mutation-tested and all four fired.*

**The user refused a one-paper conclusion, and that refusal changed the code
twice.** One paper said "everything works". Twenty-four found a silent failure
and killed a planned subsystem.


### What shipped

| module | holds |
|---|---|
| `ingest/_pdf.py` | `load_pdf(raw: bytes) -> str` and `split_pdf` — one mark per page, three refusals |
| `ingest/defaults.py` | `MIN_PDF_CHARS_PER_PAGE = 100`, `MIN_PDF_WORDS_WITH_VOWELS = 0.40` |
| `ingest/chunker.py` | `.pdf` in **both** `LOADERS` and `SPLITTERS` |
| `sources/defaults.py` | `.pdf` readable, `MAX_FILE_BYTES` 1MB -> **5MB** |
| `api/config.py` | `MAX_UPLOAD_BYTES` 1MB -> **5MB** |
| `requirements.txt` | `pypdf==6.16.2`, a **runtime** dependency |
| `data/samples/pdf/` | one fixture per variant: `one_column`, `two_column`, `type3_garbled` |

`load_pdf` writes `# %% page 4` and `split_pdf` cuts there, so a citation reads
`[paper.pdf · page 4 · lines 120-147]`. Same loader-marks / splitter-cuts split
as the notebook, and `to_pieces` is shared.


### The planned XY-cut layer was CANCELLED by measurement

The theory predicted a two-column paper would extract spliced — *"We train with
Adam at 3e-4 Table 2 reports F1 of 0.851"* — and scheduled a gutter-finding layer
to repair it.

**The splice is real, and it never reached us.** A hand-built PDF whose stream is
row-major scrambles exactly as predicted. **Nine real two-column papers did
not.** LaTeX writes one whole column and then the other, so file order already
*is* reading order, and pypdf follows file order.

The probe was calibrated before it was trusted — column switches per line:

```
synthetic row-major    (known bad)   1.98
synthetic column-major (known good)  0.03
every real paper                     0.02 - 0.48
```

Three real papers scored above the line and **all three were false positives** —
big tables and display math legitimately alternate left-right. Reading their text
settled it. **The pypdf maintainers agree**: plain mode "seems to work properly",
and `extraction_mode="layout"` is *worse* for us, because it rebuilds the visual
page and puts both columns on one line.

> **A danger proven in the mechanism may never appear in the population.**
> Measure the real inputs before building the defence. We deleted a subsystem
> instead of writing it.


### The failure one paper would never have found

`0704.0001` extracts **successfully** as:

```
/D8/D6/D3 /DB /CT/CP/CZ /D7/DD/D1/D1/CT/D8/D6/DD
```

1 paper in 24 — about 4%, so users will meet it. Nothing raises.

**And it corrects the theory.** The lesson blamed a missing `/ToUnicode` CMap:

```
0704.0001  (garbage)  9 fonts, 6 WITH /ToUnicode, Type1 + Type3
1512.03385 (perfect)  6 fonts, 0 with /ToUnicode, Type1 only
```

**ResNet has no `/ToUnicode` at all and is perfect.** The real cause is **Type3**
fonts — old dvips bitmap glyphs whose names carry no Unicode meaning.


### Detect the symptom, not the cause — and the first detector was wrong

The first detector counted **letters against all characters**. It separated the
files, but only by 1.5x, and the user asked whether the threshold was too high.
It was, and measuring proved it:

```
pages under a 0.70 letter ratio:  67 of 596  -- nearly all legitimate
worst: CLIP page 40 at 0.259, a page of pure results tables
```

**A results table is mostly digits, and that is normal.** The check would have
refused honest papers.

The better question is not *"how many letters?"* but **"do the words contain
vowels?"** Real words do; glyph names like `CT`, `CZ`, `DB` do not. And numbers
are skipped entirely, because a number is not a word:

| | letters ratio | **vowel-word ratio** |
|---|---|---|
| garbled file | 0.546 | **0.129** |
| worst good file | 0.841 | **0.948** |
| separation | 1.5x | **7x** |

Per page, over 596 pages: the worst ten are **all** the garbled file
(0.090-0.108), the lowest good page is **0.516**, and **0 of 559** good pages
fall under 0.50. So `MIN_PDF_WORDS_WITH_VOWELS = 0.40` has room on both sides.

> **When a check refuses honest input, do not lower the threshold — change the
> question.** Counting letters asked about characters. Counting vowels asked
> whether the output is language.


### The three refusals, and why each exists

| guard | catches | why |
|---|---|---|
| `PdfReadError` -> `LoaderError` | not a PDF, truncated, no xref | measured on six kinds of broken input: pypdf raises `PdfReadError` or a subclass **every** time, so nothing wider is caught |
| chars/page < 100 | **scanned** PDFs | a scan returns an empty string and raises nothing. Real pages run 812-5,000 chars |
| vowel-words < 0.40 | **Type3** fonts | extraction succeeds and returns glyph names |

Plus one repair rather than a refusal: `unicodedata.normalize("NFKC", ...)` folds
`U+FB01` back to `fi`, or a citation quoting "fit" could never match the stored
"ﬁt".


### The two limits had to move together

`MAX_UPLOAD_BYTES` and `MAX_FILE_BYTES` both went to 5MB. Raising only the upload
limit would let `.pdf` into `READABLE_SUFFIXES` while every real paper inside a
repository was skipped as `too big` — a silent drop through the other door. The
slice-2 archive `xfail(strict=True)` was checked and **stays xfail**: 50MB is
still above the new ~10MB body limit.

**Four size tests went red, and that was them working.** Each carries a literal
payload plus `assert len(huge) > THE_CONSTANT`, exactly as the 2026-08-17 rule
requires, so raising a limit fails loudly instead of passing forever.


### Honest limits

- **All 24 papers are arXiv, so all are LaTeX** (pdfTeX, or dvips + Ghostscript).
  Word and InDesign PDFs are **untested**. The splice failure is real and we
  simply never met it; a non-LaTeX producer could still bring it.
- **1 paper in 24 is unreadable to us.** That is the honest hit rate.
- Minor artifacts left unfixed: spurious spaces inside words (`combi ning`), and
  figure labels arriving as short junk lines.


### Mutation results — all four fired

| mutation | fired |
|---|---|
| `MIN_PDF_WORDS_WITH_VOWELS = 0.0` | the Type3 refusal test, **alone** |
| `MIN_PDF_CHARS_PER_PAGE = 0` | both scanned tests, unit and api |
| delete the `NFKC` call | the ligature test and the chunker test |
| remove `.pdf` from `LOADERS` | the three tests that go *through* the registry |

The last one also proved the fallback stays **loud**: with no loader a PDF fails
as "not UTF-8", never silently.


### The review pass — three tests written, two deleted

*Run at the close of `.pdf`, asking only the standing question: **which real
failure is still unprotected?** Three candidates were written, mutation-tested,
and **two were deleted for being dead.* **480 passed, 28 skipped, 2 xfailed.**

**Kept — it fires alone:**
`test_a_real_paper_in_a_repository_is_ingested_not_skipped_as_too_big`. Real
papers are 0.8-2.2MB, and `MAX_FILE_BYTES` had to rise to 5MB for the
**repository** door. Nothing tied that constant to a real file: only
`MAX_FILE_BYTES <= MAX_UPLOAD_BYTES`, which is two constants agreeing with each
other. Reverting the limit to 1MB makes this test — and **only** this test — go
red. Without it, every paper inside a repository would be dropped as `too big`,
and a skip raises nothing.

**Deleted — a PDF cap test and a PDF verbatim-slice test.** Both looked
reasonable and both failed the real question. Seven mutations were tried,
including three aimed at PDF alone:

```
cap pass never splits          -> fired with 3 existing tests
parts lose the line offset     -> fired with 4 existing tests
pages joined with one newline  -> nothing fired
the page mark is dropped       -> fired 5 tests, NEITHER new one
_readable stops stripping      -> nothing fired
merge uses raw, not loaded     -> only an EXISTING test fired
```

**Neither ever fired alone.** The quora fixture already exercises both
invariants — `class Trainer` is 5,300 tokens against a 1,530-character cap — so
running the same assertions over a second corpus adds a number and no
protection.

> **A new corpus is not a new invariant.** Re-asserting a rule you already test,
> on different data, buys nothing. Only a rule nothing else checks is worth a
> test — and the way to find out is to break the code, not to read the test.

Also refused deliberately: a *"broken PDF in a repository is skipped and
counted"* test. It is the same `except LoaderError` branch the notebook test
already pins, so it would be one test per **combination** rather than per
failure.


### A process failure worth more than the code

Mutation testing was run **while the user was merging branch to branch**, and
`git checkout -- <file>` restored a file to a `main` that had never received the
new constants. **The undo became a delete**, and 18 test modules went red.

CLAUDE.md already said *"commit before mutating, or the undo step is a delete
step."* That was not enough: the tree **was** clean when the check ran, and the
branch moved afterwards.

> **Never restore a mutation with git. Copy the file aside and restore from the
> copy.** A file copy cannot be invalidated by a branch someone else moves.
> `git checkout --` restores to whatever HEAD is *now*, not to what you saved.

The second half of the same incident: the file-by-file merge left `<<<<<<< HEAD`
markers in three files with **no `MERGE_HEAD`**, so git gave no warning at all —
the only symptom was 25 collection errors.


### What slice 3 still owes

- **~~`.docx`~~ DONE — see [the .docx results](../../step1/document-formats.md#docx--done-2026-08-30-measured-on-18-real-word-files).
  Only **other code languages** remain: they are plain text, need no loader at
  all, and need only **one** generic splitter.**
- ~~**The `MAX_CHUNK_TOKENS` cap bug is still untouched**~~ **DONE 2026-09-05 —
  see [the chunk cap fix](../../step1/vector-store.md#the-chunk-cap-fix--2026-09-05-the-last-cheap-moment).**
