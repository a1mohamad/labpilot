# Step 1, slice 3: document formats

[Docs home](../README.md)

## Slice 3, first half - DONE 2026-08-29: a notebook becomes cells

**`.ipynb` was the one input this project accepted and silently mangled** (JSON decodes as UTF-8, passes the gate, and
chunk 7 of the user's `02-train.ipynb` read `_SIMILARITY_PARM\n", "  if "Q1" in param...`).

### What the file actually is, measured

Raw `02-train.ipynb`: 123,461 chars / 41,154 est tokens — cell source 44.9%, output TEXT 22.9% (**the run numbers live
here**), JSON scaffold 32.2% (pure noise). **Only 45% of a notebook file is the code.**

### The result, end to end on that notebook

As raw JSON → loaded: chunks 94 → **91**; tokens 45,756 → **28,451** (38% fewer); chunks with escaped JSON most → **0**;
chunks with a cell label 0 → **91**; chunks carrying run output 0 → **23**. Signal share is `alpha = f/s`, so cutting `s` by
38% raises it by `1/(1 - 0.38)`: alpha_loaded ≈ **1.6×** alpha_raw. (The lesson delivered beforehand predicted "roughly
doubles"; the smaller true number is the one that survives.)

### What shipped

`ingest/errors.py` (`LoaderError`: a loader can fail on bad data where a splitter cannot), `ingest/_notebook.py`
(`load_notebook` JSON → text, `split_notebook` text → cells), `ingest/_sections.py` (`to_pieces`, the section logic
`_markdown` and `_notebook` both had), and a **`LOADERS` dict beside `SPLITTERS`**, applied in `chunk_bytes`.

### Five decisions worth keeping

1. **Loading runs in `chunk_bytes`, not `chunk_file`.** An upload arrives as content through `api/uploads.py`, never as a
   path; loading in `chunk_file` would have fixed the repository door and left the API door mangling notebooks.
2. **Images are dropped by construction, not by a filter.** `display_data` reads only `data["text/plain"]`; an image
   output has none, so it yields `""`. No mime blocklist to maintain.
3. **Outputs are kept** (the `quora_siamese` lesson: the run numbers exist only in stored outputs). `error` outputs are
   kept as `ValueError: shape mismatch` (a cell that failed is a divergence signal); `execution_count` is recorded as
   `run 7` or `not run` (a cell that never ran may hold stale code).
4. **`_join` joins with `""`, never `"\n"`.** nbformat stores each line *with* its trailing newline; joining with `"\n"`
   doubles every line break, silently.
5. **The loader marks; the splitter cuts.** `load_notebook` writes `# %% cell 12 [code] run 7`, `split_notebook` cuts there,
   so the splitter never needs the JSON.

### Two real bugs the wiring created, both found by the review pass

Both are **a new error type crossing an old boundary that does not know it.** A malformed `.ipynb` uploaded to `/compare`
reached the 500 handler (`LoaderError` is not an `ApiError`) → now **422 `unreadable_upload`**; a malformed `.ipynb` inside a
repository made `chunk_source` (which caught only `UnicodeDecodeError` and `OSError`) **lose every file after it, silently,
because it is a generator** → now skipped and counted as `unreadable document` (the slice 2 audit's defect, reintroduced
through a newer door within one slice). **When you add an error type, walk every boundary that already catches errors.**

### The registry rule is now a test, not a sentence

`test_every_format_we_can_read_is_also_a_format_we_can_fetch` asserts `set(LOADERS) <= READABLE_SUFFIXES` and the same for
`SPLITTERS`: a suffix in `LOADERS` but not readable is a handler `sources/` silently skips; readable but no splitter is a
file walked in and then cut blindly. **Prose rots; the build now fails instead.**

### `_sections.py` - the extraction the rule prescribed

`_markdown` and `_notebook` had character-identical `_sections` and `_pieces`; once the second case existed they were
extracted into `to_pieces(lines, marks)`, each splitter supplying only how it finds a boundary. The existing tests passing
unchanged proved the refactor safe.

### What slice 3 has NOT done yet

*(History, all since done.)* `.pdf`, `.docx` and other languages followed. The `MAX_CHUNK_TOKENS` cap applied to `chunk.text`,
not `chunk.embed_text` (5 of 91 notebook chunks over once the header was added) was deliberately deferred to its own pass and
**fixed 2026-09-05** (see "The chunk cap fix"). `MAX_UPLOAD_BYTES` rose from 1MB to 5MB for PDFs.

## Slice 3, second half — `.pdf`: the theory, recorded 2026-08-30

*Session 14 wrote no `.pdf` code on purpose; the lesson changed the design (the loader signature was wrong for every binary
format). Every claim was demonstrated on a two-column PDF written by hand with the standard library, which proves the
**mechanism**, not any library.*

### The concept — a PDF is a photograph, not a recipe

PDF is a page description language: it stores instructions for painting ink at coordinates, not the document. A `.py` is a
recipe; a PDF is a photograph of the finished page where the text is still selectable. Reading it is **reconstruction, not
decoding** — the first input where the loader **guesses**. **A PDF loader can succeed and return garbage, and nothing
raises** (every earlier failure was loud).

### The mechanism — what is really in the file

Numbered objects (Catalog → Pages → Page → a content stream); the stream is a small stack program
(`BT /F1 10 Tf 1 0 0 1 72 700 Tm (We train with Adam at 3e-4) Tj ... ET`). **There is no paragraph, heading, column or
reading order in the file.** Three reasons text is hard to recover: (1) the stream is compressed (`FlateDecode`), so a PDF
is binary even though its skeleton is ASCII (`'utf-8' codec can't decode byte 0x9c`); (2) the string holds font codes, not
Unicode (subsetted fonts need a `/ToUnicode` CMap; ligatures `fi`/`fl` are one glyph) — **CORRECTED 2026-08-30 by
measurement: a missing `/ToUnicode` is NOT the cause** (ResNet has zero maps and extracts perfectly; the file that really
broke uses **Type3** fonts), while the ligature half was right (`U+FB01` had to be folded); (3) file order is not page
order. So extraction is six steps (parse, decompress, run the operators, map codes to Unicode, collect
`(string, x, y, size)`, **sort into a reading order**); steps 1-5 are mechanical and **step 6 is a guess**.

### The math

**a) Position is a matrix.** `T_m = [[a b 0],[c d 0],[e f 1]]` and `[x_dev y_dev 1] = [x_text y_text 1] · T_m · CTM` (`a, d`
scale, `b, c` skew/rotate, `e, f` translate; `CTM` is the page's transformation matrix; `y` grows **upward**).

**b) Reading order.** Naive rule: `i ≺ j ⇔ (y_i > y_j) ∨ (y_i = y_j ∧ x_i < x_j)`, with line bucketing of tolerance ≈ `0.3 h`.
Two columns break it, because a left and a right line sit at the same `y` (you read 1 2 3 4 5 6, the machine reads
1 4 2 5 3 6). With `C` columns and `L` lines per column a *break* is two output neighbours that were not neighbours in
truth: `breaks_correct = C - 1`, `breaks_naive ≈ C·L - 1`; a normal page (`C = 2`, `L ≈ 45`) goes from 1 break to ~89. The
six-line demo measured the extreme: naive 5 of 5 wrong, column-aware 0 of 5.

**c) The fix, layout analysis (XY-cut).** Let `f(x)` be how many items cover horizontal position `x`; a gutter is
`f(x) = 0` on `[x1, x2]` with `x2 - x1 > g_min ≈ 0.02 W`; cut, sort each side alone, join. *(A correction made in-session: the
demo first reported a 41% gutter because the fake lines had a start but no width; the real figure was ~5%. A number from a
fixture with missing fields is a number about the fixture.)* **This layer was CANCELLED by measurement; see ".pdf — DONE".**

**d) The scanned PDF — refuse it.** A scan is images with no text operators; extraction returns `""` **successfully**.
OCR needs a model (the 512MB budget forbids it), so refuse by density: `characters extracted / pages < τ ⇒ refuse`; a normal
page is 2,000-3,000 chars, so τ near 100 is *probably* safe — **measured, not chosen** (done: 100).

### Loaders take bytes — decided 2026-08-30

*(Built the same day; the outcome is in "Loaders take bytes — DONE".)* `LOADERS` was typed `Callable[[str], str]` and both
doors decoded UTF-8 *before* the loader ran, so a real paper died at the door as "not UTF-8 text" and the loader was never
reached. Three options: **A — loaders take bytes** (`Callable[[bytes], str]`, both doors stop decoding, UTF-8 becomes the
**default loader**) · B — a second binary door (**two paths**: the exact shape that produced both slice-3 wiring bugs) · C —
decode as latin-1 (silent corruption). **A won on evidence, not taste: the design note already said "give me text from these
**bytes**".** `.py` and `.ipynb` had merely hidden the step. A free win: one decoder, one error, both doors.

### Why A also settles `.docx` and the other languages

**Binary → write a loader. Text → the default handles it. Everyone needs a splitter.** `.docx` is a ZIP of XML (fails
`decode("utf-8")` like a PDF) so it is one more `LOADERS` entry; other code languages are plain text and need no loader and
only **one** generic splitter, not one per language.

### Loaders take bytes — DONE 2026-08-30

Shipped the same day with no behaviour change for existing formats (463 passed): `ingest/errors.py` gained
**`NotUtf8Text(LoaderError)`**; `ingest/_plain.py` is **new** (`load_text(raw: bytes) -> str`, the default loader and the
project's only decoder); `load_notebook` takes bytes; `LOADERS: dict[str, Callable[[bytes], str]]`; **`chunk_text` was renamed
`chunk_bytes`** (keeping both names would be a second door); `Artifact.text: str` became **`Artifact.raw: bytes`**;
`api/uploads.py` stops decoding; `chunk_source` catches `NotUtf8Text` **before** `LoaderError`. `_load` and `_split` are now the
same shape (`LOADERS.get(suffix, load_text)(raw)` and `SPLITTERS.get(suffix, split_recursive)(text)`).

#### Centralising the decoder found a live bug nobody was looking for

A UTF-8 **byte-order mark** (`EF BB BF`, prepended by Windows editors) makes `ast.parse` fail, and `_python.py` then falls
back to `split_recursive`: **a Python file saved with a BOM lost every function and class boundary, silently** (labels
`['def add']` became `['']`; the markdown `^#` regex failed the same way; and citations break because a BOM sits inside line
1). The fix is four letters: decode with **`utf-8-sig`**, never `utf-8` (it strips one leading BOM, is identical when there
is none, and cannot change *whether* a file decodes). **Only decode with it: writing with it ADDS a BOM**, so the one
`.encode("utf-8")` in `body_limit.py` stays plain. **One decoder is one place to be right.**

#### Why there are two error types and not one

`NotUtf8Text` exists because `chunk_source` **branches** on it (a test pins `skipped == {"not utf-8": 1}`), and `walk`
screens by **suffix**, not content, so a latin-1 `.py` really reaches the chunker. **The `except` order carries the whole
distinction and Python never warns you:** the subclass must be caught **first**, or every encoding problem is filed as
`unreadable document`.

#### Two bugs, and the second one is the lesson

`load_text` missing its `return` cost **61 failed + 15 errors** (every message said `None`): **group failures by their message
before reading any of them — sixty-one failures carrying one message is one bug.** A test that mocked `Path.read_text` stopped
testing anything once `chunk_file` called `read_bytes`: **when you move an I/O call, every test that mocked the old call stops
testing anything.** And a mocked name written as a string (`monkeypatch.setattr(Path, "read_text", ...)`) is invisible to
every rename — search for the string, not the variable.

#### The invariant that will pay for itself at `.pdf`

`test_a_loader_refuses_what_it_cannot_read_with_our_own_error` parametrizes over `LOADERS` and hands each a PNG header: a
registered loader must raise `LoaderError`, never crash and never return junk. `.pdf` and `.docx` inherited it the day they
were added (it is deliberately *not* "every loader refuses non-UTF-8": a PDF loader must accept binary). `.pdf` then cost one
new module (`_pdf.py`, `load_pdf(raw) -> str`), one `LOADERS` line, and `READABLE_SUFFIXES` + `SPLITTERS` together.

## `.pdf` — DONE 2026-08-30, measured on 24 real papers

*The theory (session 14) had never touched a library. **480 passed, 28 skipped, 2 xfailed; all four new invariants
mutation-tested.*** **The user refused a one-paper conclusion, and that refusal changed the code twice:** one paper said
"everything works"; twenty-four found a silent failure and killed a planned subsystem.

### What shipped

`ingest/_pdf.py` (`load_pdf(raw: bytes) -> str` and `split_pdf`: one `# %% page 4` mark per page, three refusals, so a
citation reads `[paper.pdf · page 4 · lines 120-147]`; same loader-marks / splitter-cuts split as the notebook, `to_pieces`
shared) · `ingest/defaults.py` (`MIN_PDF_CHARS_PER_PAGE = 100`, `MIN_PDF_WORDS_WITH_VOWELS = 0.40`) · `.pdf` in **both**
`LOADERS` and `SPLITTERS` · `sources/defaults.py` (`MAX_FILE_BYTES` 1MB → **5MB**) · `api/config.py` (`MAX_UPLOAD_BYTES`
1MB → **5MB**; now 10MB) · `pypdf==6.16.2` a **runtime** dependency · `data/samples/pdf/` fixtures `one_column`,
`two_column`, `type3_garbled`.

### The planned XY-cut layer was CANCELLED by measurement

The theory predicted a two-column paper extracts spliced. **The splice is real, and it never reached us:** a hand-built
row-major PDF scrambles exactly as predicted, but **nine real two-column papers did not** — LaTeX writes one whole column
and then the other, so file order already *is* reading order and pypdf follows file order. The probe (column switches per
line) was calibrated first: synthetic row-major 1.98, synthetic column-major 0.03, every real paper 0.02-0.48; three real
papers scored above the line and **all were false positives** (big tables and display math legitimately alternate). The pypdf
maintainers agree: plain mode "seems to work properly" and `extraction_mode="layout"` is *worse* for us. **A danger proven
in the mechanism may never appear in the population; measure the real inputs before building the defence.** We deleted a
subsystem instead of writing it.

### The failure one paper would never have found

`0704.0001` extracts **successfully** as `/D8/D6/D3 /DB /CT/CP/CZ ...` (1 paper in 24, ~4%, nothing raises). It corrects the
theory: it has 9 fonts, 6 *with* `/ToUnicode`, Type1 + Type3, while the perfect ResNet has 6 fonts and **none** with
`/ToUnicode`. The real cause is **Type3** fonts (old dvips bitmap glyphs whose names carry no Unicode meaning).

### Detect the symptom, not the cause — and the first detector was wrong

The first detector (letters against all characters) separated the files by only 1.5x and would have refused honest papers:
67 of 596 pages fell under a 0.70 letter ratio (worst: CLIP page 40, pure results tables at 0.259). **A results table is mostly
digits, and that is normal.** The better question is **"do the words contain vowels?"** (glyph names like `CT`, `CZ`, `DB`
do not; numbers are skipped): garbled file 0.129 vs worst good file 0.948, a 7x separation; the ten worst pages are all the
garbled file (0.090-0.108), the lowest good page is 0.516, and **0 of 559** good pages fall under 0.50, so
`MIN_PDF_WORDS_WITH_VOWELS = 0.40` has room on both sides. **When a check refuses honest input, do not lower the threshold —
change the question.**

### The three refusals, and why each exists

`PdfReadError` → `LoaderError` (not a PDF, truncated, no xref; measured on six kinds of broken input, pypdf raises
`PdfReadError` or a subclass every time, so nothing wider is caught) · **chars/page < 100** (a **scanned** PDF returns an
empty string and raises nothing; real pages run 812-5,000) · **vowel-words < 0.40** (**Type3** fonts: extraction succeeds and
returns glyph names). Plus one repair, not a refusal: `unicodedata.normalize("NFKC", ...)` folds `U+FB01` back to `fi`, or a
citation quoting "fit" could never match the stored "ﬁt".

### The two limits had to move together

`MAX_UPLOAD_BYTES` and `MAX_FILE_BYTES` both went to 5MB: raising only the upload limit would let `.pdf` into
`READABLE_SUFFIXES` while every real paper inside a repository was skipped as `too big` — a silent drop through the other
door. Four size tests went red, and that was them working (each carries a literal payload plus
`assert len(huge) > THE_CONSTANT`, so raising a limit fails loudly instead of passing forever).

### Honest limits

All 24 papers are arXiv, so all are LaTeX (pdfTeX, or dvips + Ghostscript); **Word and InDesign PDFs are untested**, and the
splice failure could still come from a non-LaTeX producer. **1 paper in 24 is unreadable to us** — the honest hit rate.
Minor artifacts left unfixed: spurious spaces inside words (`combi ning`) and figure labels arriving as short junk lines.

### Mutation results — all four fired

`MIN_PDF_WORDS_WITH_VOWELS = 0.0` (the Type3 test alone) · `MIN_PDF_CHARS_PER_PAGE = 0` (both scanned tests) · deleting the
`NFKC` call (ligature and chunker tests) · removing `.pdf` from `LOADERS` (three registry tests; it also proved the fallback
stays loud: a PDF with no loader fails as "not UTF-8", never silently).

### The review pass — three tests written, two deleted

Three candidates were mutation-tested and **two were deleted for never firing alone**. Kept:
`test_a_real_paper_in_a_repository_is_ingested_not_skipped_as_too_big` (real papers are 0.8-2.2MB; only `MAX_FILE_BYTES <=
MAX_UPLOAD_BYTES` tied the constants together, which is two constants agreeing with each other; reverting to 1MB fails
only this test). Deleted: a PDF cap test and a PDF verbatim-slice test (the quora fixture already exercises both invariants —
`class Trainer` is 5,300 tokens against a 1,530-char cap). **A new corpus is not a new invariant; re-asserting a rule you
already test on different data buys nothing.** Also refused: a "broken PDF in a repository is skipped and counted" test (the
same `except LoaderError` branch the notebook test pins: one test per combination, not per failure).

### A process failure worth more than the code

Mutation testing ran while the user was merging branch to branch, and `git checkout -- <file>` restored a file to a `main`
that had never received the new constants: **the undo became a delete** and 18 test modules went red. The tree *was* clean
when the check ran; the branch moved afterwards. **Never restore a mutation with git: copy the file aside and restore from the
copy** (`git checkout --` restores to whatever HEAD is *now*). The same incident: a file-by-file merge left `<<<<<<< HEAD`
markers in three files with no `MERGE_HEAD`, so git gave no warning — the only symptom was 25 collection errors.

### What slice 3 still owes

*(History.)* `.docx` and the other code languages followed (below); the `MAX_CHUNK_TOKENS` cap bug was fixed on 2026-09-05
([the chunk cap fix](vector-store.md#the-chunk-cap-fix--2026-09-05-the-last-cheap-moment)).

## `.docx` — DONE 2026-08-30, measured on 18 real Word files

*Far smaller than `.pdf`, because every PDF problem disappears: a `.docx` stores the text itself, in reading order, as
Unicode — no columns, no glyph codes, no scanned variant. **496 passed; all eight new invariants mutation-tested.***

### What a `.docx` is

A ZIP of XML (`word/document.xml` holds the text). A paragraph is `<w:p>`; a *run* `<w:r><w:t>` is text with one style, and a
new run starts whenever the style changes.

### No library. Stdlib reads all 18 files

`zipfile` + `xml.etree` parsed every file with zero failures; `python-docx` would have been a runtime dependency buying
nothing against the 512MB ceiling.

### There is NO `.docx` splitter, and that was decided by measurement

The plan was to cut on Word heading **styles**. Counted: 6 real Word papers → 5 have no heading styles at all (the 6th has 2 in
234 paragraphs); 12 of the user's own files → 2 use `Heading1`, 10 use none. **Authors format headings by hand (bold, bigger)
instead of applying the style**, so a heading splitter would almost never fire. What replaced it is one line in the loader,
`"\n\n".join(paragraphs)`: a blank line between paragraphs makes the default `split_recursive` break on a paragraph, not
mid-sentence. `.docx` is in `LOADERS` and deliberately **not** in `SPLITTERS` (same shape as the XY-cut cancellation: the
design predicted a feature; the real files said it would never fire).

### The one thing the loader must get right: runs

Word splits a sentence across runs whenever formatting changes (one fixture line became 15 `<w:t>` runs; one paragraph began
with runs `"T"` then `"his paper"`; paragraphs split across runs per document: 105, 88, 77, 75, 57, 50, 38, 30, 24, 1, 0).
**Join runs with `""` and paragraphs with `"\n\n"`** — joining runs with a space turns `This paper` into `T his paper`, the
family of the notebook `_join` bug. `<w:tab/>` becomes a tab and `<w:br/>` a newline, so two table cells never fuse into `NameValue`.

### A new attack surface: the .docx zip bomb

A `.docx` is a ZIP arriving through a different door than `sources/archive.py` guards, and `ZipFile.read` decompresses fully
into memory (real papers 44KB → 266KB, ratios 5-14x; a crafted archive 48KB → 50MB, ratio 1028x).
`MAX_DOCX_XML_BYTES = 10_000_000`, checked against `ZipInfo.file_size` from the **header** (so the size is known before a byte
is decompressed), 37x the largest real file. **Every new format is a new door: ask which guard the other doors already have
that this one does not.**

### The three refusals, all measured

`zipfile.BadZipFile` (empty, plain text, PNG, PDF, truncated all raise it) · `KeyError` on `word/document.xml` (a ZIP that is some
other Office file) · `ET.ParseError` (broken XML). No density or vowel guard is needed: a `.docx` with no text returns `""`,
`chunk_bytes` yields nothing, and the API already answers a **422 `empty_artifact`**.

### A tab is kept, not converted to a space

The first version turned `<w:tab/>` into a space (fearing a long tab-separated row would have no break point). Measured on the
real paper: 16 tabbed paragraphs, 0 over the cap, the longest 1,821 chars with 300 spaces — the danger never materialises and a
tab keeps table columns visible. The test was renamed with it.

### Mutation results — eight, all caught

Joining runs with a space (3 tests), paragraphs with one `\n`, no bomb guard, dropping the tab, not catching a missing
`word/document.xml`, not catching broken XML, removing `.docx` from `LOADERS` and from `READABLE_SUFFIXES` — each fired the
test meant to catch it. Two lessons: `ET.ParseError` is a **subclass of `SyntaxError`**, so the first "stop catching broken
XML" mutation still caught the error and looked like a dead test — **a surviving mutation is not a verdict either; prove the
mutation changed behaviour first.** And every `.docx` test called `load_docx` directly, so removing the suffix from `LOADERS`
broke nothing: `test_a_word_paper_becomes_chunks_through_the_registry` goes through `chunk_bytes` and now fires alone.

### The review pass — two rules that were prose and nothing else

**`test_no_runtime_requirement_would_blow_the_memory_budget`:** this file said since 2026-08-11 that installing `torch` is "the
single decision that would end the free tier instantly" (300-500MB resident against 512MB) and nothing checked it. Runtime only:
`requirements-dev.txt` may hold heavy packages (the local ONNX reranker is a dev dependency that never ships).
**`test_every_committed_fixture_names_its_source_and_its_licence`:** slice 3 added 4.7MB of third-party binaries (three arXiv
PDFs and a CC-BY Word paper); `data/samples/SOURCES.md` records source and licence for each, and the test fails the build if a
binary is committed without provenance. **A rule written in a document is a rule that will be broken.**

### What `.docx` deliberately did NOT get

No API test and no repository-walk test: one test per combination (the PDF upload test and the real-paper test already pin
those paths).

### Honest limits

The tab decision rests on **one paper**; a tab-separated row over 1,530 characters with no spaces would fall to blind
fixed-size cuts. `.doc` (the old binary format) is not supported and refuses loudly. Tables arrive as one paragraph per cell
(a vertical list).

## Other code languages — DONE 2026-08-31, and the overlap bug they exposed

*The smallest job in slice 3: these files are plain text, so they need **no loader and no splitter**, only suffixes. Reading
real code to confirm that exposed a chunker defect live since slice 3 began. **502 passed.***

### 57 suffixes, no code

`sources/defaults.py` splits its registry: `CODE_SUFFIXES` (50 then, 58 after web files: `.js .ts .java .go .rs .cpp .cs .rb
.php .swift .kt .r .jl .m .sql .sh .yaml .toml ... .py`), `DOCUMENT_SUFFIXES` (7: `.md .markdown .txt .rst .ipynb .pdf
.docx`) and `READABLE_SUFFIXES` (the union). **Three deliberate exclusions, each pinned by a test:** **`.env`** (holds API keys:
never read, chunked, embedded or sent to a provider), `.json` (a pretty-printed dataset has short lines, so the generated-file
guard would not catch it) and `.csv` / `.xml` / `.lock` (data and generated output). `test_a_file_that_could_hold_secrets_or_data_is_never_readable`
fires alone when `.json` is added (`.env` also trips an older test, but only because `env` is a skipped directory name).

### No splitter, and that was measured

Real Go through `split_recursive`: 38 chunks, 534-1496 characters, correct line numbers; blank lines between functions already
give roughly function-level breaks. A per-language splitter would be toil for no measured gain.

### The minified-file guard

The walk filters by suffix and size only, so `bundle.min.js` walked straight in: 65 chunks, every one reporting lines (1, 1), a
chunk reading `'e[f]=e[f]*2}return e};function a(b,c){return b+'`. Those citations are not *wrong* (a chunk on line 1 truthfully
reports line 1); they are **useless** — a finding "at line 1" of an 87KB single line locates nothing. **The threshold moved
once, and the first number was bad:** 500 mean chars per line, chosen from source code alone (1,386 real source files: mean
31.8, p99 47.5, worst 69.0), but prose was never measured (286 prose files, worst mean 176.5) and it fired on an existing test.
It is now **derived from the thing that breaks**: `MAX_MEAN_LINE_CHARS = MAX_CHARS` (1,530) — a mean line longer than one
whole chunk means chunks live *inside* a line (8.7x above the worst prose, 22x above the worst code, 28x below `jquery.min.js`
at 43,766). **When a threshold refuses honest input, do not nudge it — anchor it to the thing that breaks.**
`LooksGenerated(LoaderError)` gives the walk a distinct count (`generated or minified`, a counted skip) and the API a 422.

### The gap this guard does NOT close, stated plainly

It is a **file-level** rule. 600 normal lines plus one 60,000-character line has mean 106, passes, and leaves 41 of 91 chunks stuck
inside line 601. Refusing the whole file would throw away 550 good lines, so refusing is the wrong answer: those chunks are
correctly located and merely low-resolution. Left alone on purpose and recorded so it is not rediscovered as a surprise.

---

## The overlap fix — 10.8% of chunks began inside a word

*Found while reading real Go, not by any test.* `_pack` set each chunk's start to `block_start - OVERLAP_CHARS`, a **raw
character count** that lands anywhere (`'ntextRequestKey ContextKeyType = 0'`, "Co" left behind). Before: **24 of 222 chunks
began mid-word (10.8%)**; after: 0 of 226. The fix is `_snap`: move the overlap start back to the beginning of a line, or
failing that past a space, never below the floor that keeps the chunk inside `MAX_CHARS` (six lines).

### The test that promised both ends and checked one

`test_a_word_is_never_cut_in_half` passed the whole time because it asserted only `p.text.endswith("word")`; the unchecked end
was exactly where the bug lived. It is now `test_a_piece_never_begins_or_ends_inside_a_word`, asserting a real word boundary at
both ends, and reverting `_snap` makes only it fail. **A test named after an invariant must check the whole invariant, not the
convenient half** (same family as `test_no_chunk_text_exceeds_the_hard_cap`). A correction worth keeping: my first replacement
asserted `startswith("word")` and failed because every fixture paragraph begins with "paragraph" — the code was right and the
assertion was wrong; *read the failure before blaming the code.*

### The re-score, which is why the fix was safe to make now

Boundaries moved (`B_train.py` 78 → 79 chunks), so slice 1's numbers described chunks that no longer existed. Re-run with
`codestral-embed`: recall@1 0.412 / @5 0.941 / @10 0.941 unchanged, MRR 0.613 → 0.623; `D2` still rank 42. **Cheap only because
nothing was embedded yet** (four embedding requests); after slice 4 the same change would mean re-embedding every corpus.
**Fix chunk boundaries before pgvector exists, or not at all.**

### `scripts/retrieval/score_retrieval.py` is now committed

Slice 1's scorer lived in a session scratchpad and was lost. `PYTHONPATH=. python scripts/retrieval/score_retrieval.py` (four embedding
requests, no generation quota). **A measurement you cannot repeat is a number, not a result; the instrument belongs in the
repository beside the fixture.**

### The slice 3 closing review — one door had no guard at all

*(505 passed.)* **Web files were an omission, not a decision:** `.html .css .scss .sass .less .vue .svelte .htm` were never listed
(the user noticed); measured safe (real `.css` max line 746, `.html` 287, far under 1,530; `.min.css` still caught);
`CODE_SUFFIXES` is now 58.

#### The finding: `.env` was refused by one door and accepted by the other

`READABLE_SUFFIXES` kept a credentials file out of a **repository walk**, but the **upload endpoint** only checked that a filename
*has* a suffix: `prod.env` was skipped by the walk and accepted, chunked and sent to a model provider by the upload. That is the
whole reason `.env` is excluded, and half of it was missing. `SECRET_SUFFIXES` now lives in `sources/defaults.py` (`.env`,
`.pem`, `.key`, `.p12`, `.pfx`, `.keystore`, `.jks`) and the door raises a typed `SecretUpload` (422, `secret_upload`).
**An allowlist protects the door that reads it; when a rule exists for a security reason, walk every entrance.** Three tests,
mutation-verified (dropping the door guard fires the API test alone; making `.pem` readable fires
`test_no_secret_suffix_is_also_readable` alone).

#### One test I wrote in the same pass was fake, and the mutation proved it

`test_a_readable_suffix_with_no_loader_is_really_plain_text` parametrized over 63 suffixes yet declaring `.zip` readable with no
loader did not fail it (the test feeds text and every loaderless suffix resolves to `load_text`). **Deleted** (567 → 505 tests).
**A parametrized test is not 63 tests: it is one assertion run 63 times, and if it is trivially true it is trivially true 63
times over.**

### Formats are Step 1, not Step 2, and the reason is permanence

> **The chunker is permanent. Chunk boundaries decide what is possible and nothing downstream repairs them.** A corpus embedded with bad boundaries must be
> re-chunked and re-embedded, the whole thing. That is the entire argument for slice 3 before pgvector.

Priorities: `.ipynb` (highest, stdlib `json`), `.pdf` (highest, `pypdf`), `.docx` (medium), other languages (one generic splitter). **For a notebook read the outputs, not
only the source** (the run numbers live there; the first `A_paper.md` was invented because only the code was read). **PDF extraction is lossy and must be measured**;
a scanned PDF must be **refused** (OCR breaks the memory budget). **Refuse what cannot be handled well: a real loader or a clear 422, never a silent fallback.**

### Do not use LangChain's document loaders — corrected 2026-08-20

The Architecture bullet used to allow "document loaders"; it predates the 512MB budget. **The memory rule wins for loaders.** `langgraph` needs only
`langgraph-checkpoint`, `-sdk`, `-prebuilt`, `pydantic` (+ `langchain-core`, small, **no loaders**); `PyPDFLoader` lives only in `langchain-community`
(SQLAlchemy, aiohttp, numpy, dataclasses-json, langchain). Three reasons, weakest first: output shape (`Document` objects we would convert), volume
(`langchain-community` ~120-200MB), and the one that settles it: **LangChain does not contain the parser** (`PyPDFLoader` needs `pypdf` anyway). The argument that
would overturn it: if anything else needs `langchain-community`. **Verified 2026-09-23 (Step 2 slice 0): langgraph 1.2.12 pulls no torch, no numpy, no
langchain-community; ~55MB imported.**
