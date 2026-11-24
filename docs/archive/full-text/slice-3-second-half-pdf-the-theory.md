# Full text: Slice 3, second half — `.pdf`: the theory, recorded 2026-08-30

[Docs home](../../README.md)

## Slice 3, second half — `.pdf`: the theory, recorded 2026-08-30

*Session 14 wrote no `.pdf` code on purpose. The lesson came first, and it
changed the design: the loader signature is wrong for every binary format, and
nobody had noticed because no binary format had arrived yet.*

*Every claim below was demonstrated on a two-column PDF **written by hand with
the standard library** — the builder is in the session scratchpad. That proves
the **mechanism**. It does **not** prove any library, and no threshold here may
be chosen until a real paper is run through one.*


### The concept — a PDF is a photograph, not a recipe

**PDF is a page description language, not a document format.** It does not store
the document. It stores instructions for painting ink at coordinates.

> A `.py` file is a **recipe** — the steps, in order.
> A PDF is a **photograph of the finished page**, where the text is still
> selectable.

So reading a PDF is **reconstruction, not decoding**. Everything before it was
exact: a `.py` read as text *is* the file, and an `.ipynb` is complete JSON. This
is the first input where the loader **guesses**.

> **A PDF loader can succeed and return garbage. Nothing raises.** Every earlier
> failure in this project was loud — bad JSON, bad UTF-8. This one is silent,
> and that is the whole reason `.pdf` earns a lesson instead of a dict entry.


### The mechanism — what is really in the file

A PDF is numbered **objects**: Catalog → Pages → Page → a **content stream**.
The content stream is a small stack program:

```
BT                                  begin text
/F1 10 Tf                           font F1 at size 10
1 0 0 1 72 700 Tm                   text matrix -> position (72, 700)
(We train with Adam at 3e-4) Tj     paint this string there
1 0 0 1 320 700 Tm                  jump to the RIGHT column, same height
(Table 2 reports F1 of 0.851) Tj
ET
```

`Tj` paints a string at a position. **There is no paragraph, no heading, no
column and no reading order in the file.** Those exist only in the picture a
human sees.

Three separate reasons the text is hard to recover:

1. **The stream is compressed.** `/Filter /FlateDecode` is zlib, so decoding the
   file as UTF-8 dies on the first compressed byte — measured:
   `'utf-8' codec can't decode byte 0x9c in position 366`. **A PDF is binary,
   even though its skeleton is ASCII.**
2. **The string holds font codes, not Unicode.** Real papers use **subsetted**
   fonts, so code `3` may mean the glyph "A". Recovery needs the font's
   `/ToUnicode` **CMap**, and some LaTeX PDFs ship without one — the page looks
   perfect on screen and extracts as nonsense. Ligatures (`fi`, `fl`) are one
   glyph and often come out strange or vanish.
   **CORRECTED 2026-08-30 by measurement — a missing `/ToUnicode` is NOT the
   cause.** ResNet carries **zero** `/ToUnicode` maps and extracts perfectly,
   because a Type1 font with standard encoding maps on its own. The file that
   really broke uses **Type3** fonts. The ligature half was right: `U+FB01` is
   real and had to be folded. See
   [the .pdf results](../../step1/document-formats.md#pdf--done-2026-08-30-measured-on-24-real-papers).
3. **The order in the file is not the order on the page.** This is the big one.

So extraction is six steps — parse objects, decompress, run the operators,
map codes to Unicode, collect `(string, x, y, size)` items, and then
**sort them into a reading order**. Steps 1-5 are mechanical.
**Step 6 is a guess, and it is where papers break.**


### The math

**a) Position is a matrix, not an `x, y`.** PDF tracks a 3x3 text matrix, where
`a, d` scale, `b, c` skew and rotate, and `e, f` translate:

$$
T_m = \begin{bmatrix} a & b & 0 \\ c & d & 0 \\ e & f & 1 \end{bmatrix}
\qquad
[x_{dev}\; y_{dev}\; 1] = [x_{text}\; y_{text}\; 1] \cdot T_m \cdot CTM
$$

`CTM` is the page's current transformation matrix. A rotated or scaled page moves
every coordinate, so an extractor reading only `e` and `f` gets it wrong. Note
`y` grows **upward**, the opposite of a screen.

**b) Reading order — the failure that matters.** Given items
`(s_i, x_i, y_i, h_i)`, the naive rule is top-to-bottom then left-to-right:

$$
i \prec j \iff (y_i > y_j) \;\lor\; (y_i = y_j \;\land\; x_i < x_j)
$$

Floats never compare equal, so real code buckets lines with a tolerance
`epsilon` of roughly `0.3 h`. **And that is exactly what destroys two columns**,
because a left-column line and a right-column line sit at the *same* `y`:

```
   THE PAGE            you read        the computer reads
 +-----+-----+
 |  1  |  4  |         1 2 3 4 5 6     1 4 2 5 3 6
 |  2  |  5  |                          ^   ^   ^
 |  3  |  6  |                     jumps columns every line
 +-----+-----+
```

Measured on our file, the method and the results were spliced together:
*"We train with Adam at 3e-4 · Table 2 reports F1 of 0.851 · and clip gradients
at 1.0. · on the held-out test split, …"* — fluent, and nonsense.

Counting it: with `C` columns and `L` lines per column, a **break** is two
neighbours in the output that were not neighbours in truth.

$$
\text{breaks}_{\text{correct}} = C - 1
\qquad
\text{breaks}_{\text{naive}} \approx C \cdot L - 1
$$

A normal paper page is `C = 2`, `L ≈ 45`, so **1 break becomes about 89** —
nearly every adjacency destroyed. Our six-line demo measured the extreme:
**naive 5 of 5 wrong, column-aware 0 of 5 wrong.**

**c) The fix — find the gutter.** This is **layout analysis**; the recursive form
is the **XY-cut algorithm**. Let `f(x)` be how many text items cover horizontal
position `x`. A gutter is an empty vertical strip that is wide enough to be real:

$$
f(x) = 0 \;\; \forall x \in [x_1, x_2],
\qquad x_2 - x_1 > g_{\min} \approx 0.02 W
$$

Cut there, sort each side alone, then join. The `g_min` floor matters because the
space between two words is also "empty".

> **A correction, made in-session and worth keeping.** The demo first reported a
> gutter of "41% of the page". That was wrong: our fake lines carried a start
> position and **no width**, so it measured start-to-start (72 → 320) instead of
> end-of-left to start-of-right (~290 → 320, about **5%**). Still far above the
> 2% floor, so the method holds — but it is a reminder that a number from a
> fixture with missing fields is a number about the fixture.

**d) The scanned PDF — refuse it.** A scanned PDF is images of pages, with no
text operators at all. Extraction returns `""` **successfully** — the silent
failure in its purest form. OCR needs a model, which the
[512MB budget](../../product/memory-budget.md#memory-budget--render-free-tier-512mb) forbids, so the honest
answer is a refusal. Detect by density:

$$
\frac{\text{characters extracted}}{\text{pages}} < \tau
\;\Longrightarrow\; \text{refuse}
$$

A normal text page is 2,000-3,000 characters, so `tau` near 100 is *probably*
safe. **It must be measured on real PDFs, not chosen.** Same rule as every other
threshold in this file.


### Loaders take bytes — decided 2026-08-30

> **BUILT the same day — the reasoning below is kept, the outcome is in
> [loaders take bytes — DONE](../../step1/document-formats.md#loaders-take-bytes--done-2026-08-30).**

**The blocking discovery: `LOADERS` is typed `Callable[[str], str]`, and there is
no valid `str` to hand a PDF loader.** Both doors decode UTF-8 *before* the
loader runs, so a real paper dies at the door as "not UTF-8 text" and our loader
is never reached:

```
upload  ->  raw.decode("utf-8")     ->  Artifact(text: str)  ->  chunk_text  ->  LOADERS
file    ->  path.read_text("utf-8") ->                          chunk_text  ->  LOADERS
                   ^                                                    ^
             PDF dies here                                       never reached
```

Three options were weighed. **Option A is chosen:**

| option | means | cost |
|---|---|---|
| **A — loaders take bytes** | `Callable[[bytes], str]`; both doors stop decoding; UTF-8 becomes the **default loader** | touches both doors and `load_notebook`, once |
| B — a second binary door | keep the text path, add a bytes path beside it | **two paths** — the exact shape that produced the two slice-3 wiring bugs, where one door was fixed and the other silently mangled |
| C — decode as latin-1 | bytes survive inside a `str` | silent corruption; breaks *"refuse what you cannot handle well"* |

**A wins on evidence, not taste: this file's own design note already said it.**

> **Loader** — *"give me **text** from these **bytes**"*

The design always said bytes. `.py` and `.ipynb` merely **hid** the step, because
their bytes-to-text conversion was a plain UTF-8 decode performed outside the
dict. **PDF makes the hidden step visible, and the type finally says what was
always true.**

The shape after A:

```
before   bytes -> decode utf-8 (at the door) -> str -> LOADERS -> str
after    bytes -> LOADERS -> str
                    |-- default   decode utf-8      <- the bridge
                    |-- .ipynb    decode, then parse JSON
                    +-- .pdf      extract from binary
```

Four small moves, not a rewrite:

| what | change |
|---|---|
| the two doors | stop decoding — pass bytes through |
| `LOADERS` type | `Callable[[str], str]` -> `Callable[[bytes], str]` |
| the default | new — UTF-8 decode, and it raises the 422 when it fails |
| `load_notebook` | takes bytes, decodes on its first line |

**A free win that comes with it:** the UTF-8 error message currently lives at the
upload door, so `chunk_file` carries its own separate copy. After A there is one
decoder, so **one error, both doors** — the same consolidation `_sections.py`
bought for the splitters.


### Why A also settles `.docx` and the other languages

The two remaining slice-3 jobs split cleanly, and the rule becomes one line:

| format | binary? | loader | splitter |
|---|---|---|---|
| `.py` `.md` `.txt` | no | default UTF-8 | have it |
| `.ipynb` | no — JSON is text | have it | have it |
| **`.pdf`** | **yes** | new | recursive, probably |
| **`.docx`** | **yes — it is a ZIP of XML** | new | headings, probably |
| `.js` `.cpp` `.java` `.r` | no | default UTF-8 | **one** generic |

> **Binary -> write a loader. Text -> the default handles it. Everyone needs a
> splitter.**

**`.docx` is nearly free under A**, because it is a ZIP and fails
`decode("utf-8")` for the same reason a PDF does — one more entry in `LOADERS`.
Under option B it would force the door question to be answered *again*, which is
precisely how the notebook bugs happened.

**Other code languages need no loader at all** — they are plain text, and this
file already requires **one** generic splitter rather than one per language.


### Loaders take bytes — DONE 2026-08-30

*Option A shipped the same day it was decided. **463 passed, 28 skipped,
2 xfailed, ruff clean.** No behaviour changed for any existing format — this is
plumbing, and its whole value is that `.pdf` now has somewhere to go.*

| module | change |
|---|---|
| `ingest/errors.py` | **`NotUtf8Text(LoaderError)`** — a second error type, and it earns its place below |
| `ingest/_plain.py` | **new.** `load_text(raw: bytes) -> str` — the default loader, and the project's only decoder |
| `ingest/_notebook.py` | `load_notebook` takes bytes and decodes on its first line |
| `ingest/chunker.py` | `LOADERS: dict[str, Callable[[bytes], str]]`; **`chunk_text` renamed `chunk_bytes`**; `chunk_file` reads bytes |
| `ingest/__init__.py` | the errors join the public door, so `api/` stops reaching into `ingest.errors` |
| `api/contracts.py` | `Artifact.text: str` -> **`Artifact.raw: bytes`** |
| `api/uploads.py` | stops decoding entirely — the door now owns only HTTP concerns |
| `api/services.py` | calls `chunk_bytes`; `chunk_source` catches `NotUtf8Text` **before** `LoaderError` |

**`_load` and `_split` are now the same shape, which is the test of the seam:**

```
_load(raw, suffix)    ->  LOADERS.get(suffix, load_text)(raw)
_split(text, suffix)  ->  SPLITTERS.get(suffix, split_recursive)(text)
```

**The rename is deliberate.** `chunk_text` taking `bytes` would be a lie, and
keeping both names would be a second door — the exact option-B shape that
produced both slice-3 wiring bugs.

#### Centralising the decoder found a live bug nobody was looking for

Measured while writing the loader:

```
with BOM   ast.parse FAILED: invalid non-printable character U+FEFF
plain      ast.parse OK
```

A UTF-8 **byte-order mark** — the three bytes `EF BB BF` that Windows editors
prepend — makes `ast.parse` fail. `_python.py` catches `SyntaxError` and falls
back to `split_recursive`. So **a Python file saved with a BOM lost every
function and class boundary, silently.** Both splitters, measured:

```
python    no BOM -> labels ['def add']      BOM -> labels ['']
markdown  no BOM -> labels ['Method']       BOM -> labels ['']
```

One invisible character damages **three** stages: the AST splitter, the `^#`
header regex, and citations — because `chunk.text` must be a verbatim slice of
the file's lines, and a BOM sits *inside* line 1.

The fix is four letters: decode with **`utf-8-sig`**, never `utf-8`. It strips
one leading BOM and is byte-identical to `utf-8` when there is none. It cannot
change *whether* a file decodes — verified on latin-1 bytes and a PNG header,
which fail identically under both. **Only decode with it; when writing it ADDS a
BOM**, so the one `.encode("utf-8")` in `body_limit.py` must stay plain.

> **One decoder is one place to be right.** Two doors decoding separately gave
> this bug two places to hide, and it had been live since slice 3 began.

#### Why there are two error types and not one

`NotUtf8Text` exists because `chunk_source` **branches** on it, and an existing
test already pins the branch: `skipped == {"not utf-8": 1}`. Collapsing the two
would have turned a green test red for the wrong reason, and lost a genuinely
reachable bucket in the walk's report — `walk` screens by **suffix**, not by
content, so a latin-1 `.py` really does reach the chunker.

**The `except` order carries the whole distinction, and Python never warns you.**
`NotUtf8Text` is a subclass, so it must be caught **first**. Reversed, the
specific clause is dead code and every encoding problem is filed as
`unreadable document`.

#### Two bugs, and the second one is the lesson

| bug | cost | cause |
|---|---|---|
| `load_text` was missing its `return` | **61 failed, 15 errors** | the decode ran and its value was discarded, so every caller received `None` |
| a test mocked `Path.read_text` | 1 failed | `chunk_file` now calls `read_bytes`, so the mock intercepted nothing |

The first looks frightening and is trivial. Grouping the failures by message
showed **every one of the 76 said `None` or `NoneType`**. One word fixed all of
them.

> **Group failures by their message before reading any of them.** Sixty-one
> failures carrying one message is one bug, not sixty-one.

The second is the one to keep. The guard was never broken — `read_bytes` raises
`PermissionError`, which is an `OSError`, which `chunk_source` still catches.
Only the **test's aim** was stale.

> **When you move an I/O call, every test that mocked the old call stops testing
> anything.** Here it failed loudly, so we caught it. A looser assertion would
> have left the guard untested and the suite green.

A smaller trap sat inside it: `monkeypatch.setattr(Path, "read_text", ...)` names
the method as a **string**, so renaming the variable beside it changed nothing.
**A mocked name written as a string is invisible to every rename** — search for
the string, not the variable.

#### The invariant that will pay for itself at `.pdf`

`test_a_loader_refuses_what_it_cannot_read_with_our_own_error` parametrizes over
`LOADERS` and hands each one a PNG header: a registered loader must raise
`LoaderError`, never crash and never return junk. **`.pdf` and `.docx` inherit it
the day they are added** — the same pattern that fixed five untested models in
the smoke suite.

Note it is deliberately *not* "every loader refuses non-UTF-8 bytes". A PDF
loader must accept binary; what it must never do is fail in a way we do not own.

#### What `.pdf` costs now

```
labpilot/ingest/_pdf.py      load_pdf(raw: bytes) -> str      <- new module
labpilot/ingest/chunker.py   LOADERS[".pdf"] = load_pdf       <- one line
```

Plus `READABLE_SUFFIXES` and `SPLITTERS`, **together**, or
`test_every_format_we_can_read_is_also_a_format_we_can_fetch` goes red. **No
door question has to be answered again.**
