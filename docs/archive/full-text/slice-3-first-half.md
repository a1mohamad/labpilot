# Full text: Slice 3, first half - DONE 2026-08-29: a notebook becomes cells

[Docs home](../../README.md)

## Slice 3, first half - DONE 2026-08-29: a notebook becomes cells

**`.ipynb` was the one input this project *accepted and silently mangled*.** It
is JSON, so it decoded as UTF-8, passed the upload gate, and was cut as text.
Measured on the user's own `02-train.ipynb`, chunk 7 read:

```
_SIMILARITY_PARM\n",
    "                     if "Q1" in param or "Q2" in param)\n",
```


### What the file actually is, measured

```
raw .ipynb          123,461 chars     41,154 est tokens
  cell source        55,394   44.9%
  output TEXT        28,280   22.9%   <- the run numbers live here
  json scaffold      39,787   32.2%   <- pure noise
```

**Only 45% of a notebook file is the code.** The rest is JSON structure,
escaping, and stored output.


### The result, end to end on that notebook

| | as raw JSON | loaded |
|---|---|---|
| chunks | 94 | **91** |
| tokens | 45,756 | **28,451** |
| chunks with escaped JSON | most | **0** |
| chunks with a cell label | 0 | **91** |
| chunks carrying run output | 0 | **23** |

**38% fewer tokens for the same notebook.** Signal share is `alpha = f/s`, so
cutting `s` by 38% raises it by `1/(1 - 0.38)`:

$$
\alpha_{\text{loaded}} \approx 1.6 \times \alpha_{\text{raw}}
$$

*The lesson delivered before the measurement predicted "roughly doubles". It is
**1.6x**, not 2x. Recorded so the smaller true number is the one that survives.*


### What shipped

| module | job |
|---|---|
| `ingest/errors.py` | `LoaderError` - `ingest/` earns an error vocabulary, because a loader can fail on bad data where a splitter cannot |
| `ingest/_notebook.py` | `load_notebook` (JSON -> text) and `split_notebook` (text -> cells) |
| `ingest/_sections.py` | `to_pieces` - the section logic `_markdown` and `_notebook` both had |
| `ingest/chunker.py` | a **`LOADERS` dict beside `SPLITTERS`**, applied in `chunk_bytes` |

**453 passed, 28 skipped, 2 xfailed, ruff clean.**


### Five decisions worth keeping

**1. Loading runs in `chunk_bytes`, not `chunk_file`.** An upload arrives as
*text* through `api/uploads.py`, never as a path. Loading in `chunk_file` would
have fixed the repository door and left the API door mangling notebooks - and
nothing would have said so.

**2. Images are dropped by construction, not by a filter.** `display_data` reads
only `data["text/plain"]`. An image output has no `text/plain`, so it yields
`""` and disappears. There is no mime blocklist to keep up to date.

**3. Outputs are kept, and that is the `quora_siamese` lesson applied.** The run
numbers exist *only* in stored outputs; the first `A_paper.md` was invented
because only cell source was read. `error` outputs are kept too, as
`ValueError: shape mismatch` - a cell that **failed** is a divergence signal.
`execution_count` is recorded as `run 7` or `not run`, because a cell that never
ran may hold stale code.

**4. `_join` joins with `""`, never `"\n"`.** nbformat stores each line *with*
its trailing newline. Joining with `"\n"` doubles every line break - a silent,
ugly bug that no exception reports.

**5. The loader marks; the splitter cuts.** `load_notebook` writes
`# %% cell 12 [code] run 7` and `split_notebook` cuts there. That keeps the two
**jobs** separate while they share one package, and it means the splitter never
needs the JSON.


### Two real bugs the wiring created, both found by the review pass

Neither existed before `.ipynb` became a supported input. Both are the same
shape: **a new error type crossing an old boundary that does not know it.**

| bug | was | now |
|---|---|---|
| a malformed `.ipynb` uploaded to `/compare` | **`LoaderError` is not an `ApiError`, so it reached the 500 handler** - our bug, not the user's file | **422 `unreadable_upload`** |
| a malformed `.ipynb` inside a repository | `chunk_source` caught `UnicodeDecodeError` and `OSError` but **not** `LoaderError`, so **one bad notebook lost every file after it** - silently, because it is a generator | skipped and **counted** as `unreadable document` |

The second is the slice 2 audit's *"one unreadable file aborted the whole
ingest"* defect, **reintroduced through a newer door within one slice.**

> **When you add an error type, walk every boundary that already catches
> errors.** A new exception does not appear in an old `except` clause, and the
> failure it causes is a 500 or a silent truncation - never a message naming the
> real cause.


### The registry rule is now a test, not a sentence

This file said *"add each new suffix to `READABLE_SUFFIXES` **and** `SPLITTERS`
together - never one alone."* That was prose, and prose rots.
`test_every_format_we_can_read_is_also_a_format_we_can_fetch` asserts
`set(LOADERS) <= READABLE_SUFFIXES` and the same for `SPLITTERS`. A suffix in
one and not the other is now a red build:

- in `LOADERS` but not readable -> a handler `sources/` silently skips
- readable but no splitter -> a file walked in and then cut blindly


### `_sections.py` - the extraction the rule prescribed

`_markdown` and `_notebook` had **character-identical** `_sections` and
`_pieces`. CLAUDE.md's layout rule says extract an abstraction *after the second
case exists*; it now did. `to_pieces(lines, marks)` is shared, and each splitter
supplies only *how it finds a boundary* - a regex for `#` headings, a regex for
`# %%` cell marks. The existing tests passing unchanged is what proved the
refactor safe.


### What slice 3 has NOT done yet

- **`.pdf`, `.docx`, and other code languages.** Next.
- **The `MAX_CHUNK_TOKENS` cap still applies to `chunk.text`, not
  `chunk.embed_text`.** On the real notebook, **5 of 91 chunks** exceed the cap
  once the header is added. `test_no_chunk_exceeds_the_hard_cap_once_its_header_is_added`
  is still `xfail(strict=True)` and still doing its job. **It was deliberately
  not attempted at the end of a long session**: the fix has to reserve header
  room *before* splitting, which means threading a budget through
  `split_recursive`, and it moves chunk boundaries for **every** format. The
  chunker is permanent - that change deserves its own pass with a re-measurement,
  not a tired one.
- **`MAX_UPLOAD_BYTES` is still 1MB.** It has to rise for PDFs; a notebook fits
  (the real one is 123KB).
