# Full text: Other code languages — DONE 2026-08-31, and the overlap bug they exposed

[Docs home](../../README.md)

## Other code languages — DONE 2026-08-31, and the overlap bug they exposed

*The last job in slice 3, and the smallest: these files are plain text, so they
need **no loader** and **no splitter** — only suffixes. Looking at real code to
confirm that, however, exposed a chunker defect that had been live since slice
3 began. **502 passed, 28 skipped, 2 xfailed, ruff clean.***


### 57 suffixes, no code

`sources/defaults.py` now splits its registry in two:

```
CODE_SUFFIXES       50   .js .ts .java .go .rs .cpp .cs .rb .php .swift .kt
                         .r .jl .m .sql .sh .yaml .toml ... and .py
DOCUMENT_SUFFIXES    7   .md .markdown .txt .rst .ipynb .pdf .docx
READABLE_SUFFIXES        the union
```

**Three deliberate exclusions, each pinned by a test:**

| excluded | why |
|---|---|
| **`.env`** | **holds API keys.** Must never be read, chunked, embedded, or sent to a provider |
| `.json` | a dataset is usually `.json`, and a pretty-printed one has short lines, so the generated-file guard would not catch it |
| `.csv`, `.xml`, `.lock` | data and generated output, not source |

`test_a_file_that_could_hold_secrets_or_data_is_never_readable` fires alone when
`.json` is added. The `.env` case also trips an older test only because `env` is
a skipped *directory* name — a coincidence, which is why the `.json` mutation is
the one that proves the guard.


### No splitter, and that was measured

Real Go through `split_recursive`: 38 chunks, 534-1496 characters, correct line
numbers. Blank lines between functions already give roughly function-level
breaks. **A per-language splitter would be toil for no measured gain.**


### The minified-file guard

Adding `.js` opens a door the walk never had: it filters by **suffix and size
only**, with no name filter at all, so `bundle.min.js` walks straight in.
Measured before any guard existed:

```
a minified bundle -> 65 chunks, every one reporting lines (1, 1)
a chunk reads:  'e[f]=e[f]*2}return e};function a(b,c){return b+'
```

**Correct the wording that first went into this file:** those citations are not
*wrong*. A chunk that lives on line 1 truthfully reports line 1, and `resolve()`
finds the quote. They are **useless** — a finding "at line 1" of an 87KB single
line locates nothing. That still justifies a refusal; it is a different claim.

**The threshold moved once, and the first number was bad.** It started at 500
mean characters per line, chosen from source code alone:

```
1,386 real source files    mean 31.8, p99 47.5, worst 69.0
286 real prose files       worst mean 176.5
```

Prose was never measured, and unwrapped Markdown goes higher still — 500 was a
false-refusal waiting to happen, and it fired immediately on an existing test.
So the number is now **derived from the thing that actually breaks**:

```python
MAX_MEAN_LINE_CHARS = MAX_CHARS  # 1,530
```

A mean line longer than one whole chunk means chunks live *inside* a line.
Margins: 8.7x above the worst prose, 22x above the worst code and above our own
loaded PDF and Word text, 28x below jquery.min.js at 43,766.

> **When a threshold refuses honest input, do not nudge it — anchor it to the
> thing that breaks.** Same lesson as the PDF letter-ratio, one week apart.

`LooksGenerated(LoaderError)` gives the walk a distinct count
(`generated or minified`) and the API a 422. In a repository it is a **counted
skip, not a silent drop**; on upload it is a refusal, because `CompareResponse`
has no warnings channel to put a softer answer in.


### The gap this guard does NOT close, stated plainly

It is a **file-level** rule. One enormous line inside an otherwise normal file
passes it, and still damages the file:

```
600 normal lines + one 60,000-character line
mean = 106  -> passes
41 of 91 chunks stuck inside line 601
```

Refusing the whole file would throw away 550 good lines, so refusing is the
wrong answer here. Those chunks are correctly located and merely low-resolution.
**Left alone on purpose, and recorded so it is not rediscovered as a surprise.**

