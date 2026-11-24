# Full text: `.docx` — DONE 2026-08-30, measured on 18 real Word files

[Docs home](../../README.md)

## `.docx` — DONE 2026-08-30, measured on 18 real Word files

*Written the same day as `.pdf`, and far smaller, because **every PDF problem
disappears**. A `.docx` stores the text itself, in reading order, as Unicode.
No columns, no glyph codes, no scanned variant. **496 passed, 28 skipped,
2 xfailed, ruff clean.** All eight new invariants were mutation-tested.*


### What a `.docx` is

A ZIP of XML. Rename it `.zip` and open it.

```
paper.docx
├── word/document.xml     <- the text
├── word/styles.xml
└── [Content_Types].xml
```

```
<w:p>                     a paragraph
  <w:r><w:t>We train</w:t></w:r>      a run: text with one style
  <w:r><w:t> with Adam</w:t></w:r>    the style changed, so a new run
</w:p>
```


### No library. Stdlib reads all 18 files

`zipfile` + `xml.etree` — both stdlib — parsed every file with zero failures.
`python-docx` would have been a runtime dependency buying nothing, against a
512MB ceiling.


### There is NO `.docx` splitter, and that was decided by measurement

The plan was to read Word's heading **styles** (`<w:pStyle w:val="Heading1"/>`)
and cut on sections, the way `_markdown` does. Then the files were counted:

```
6 real Word papers   5 have NO heading styles at all
                     the 6th has 2 headings in 234 paragraphs
12 of the user's own files   2 use Heading1, 10 use none
```

**Authors format headings by hand — bold and a bigger font — instead of
applying the style.** Word never forces them to. So a heading splitter would
almost never fire.

What replaced it is one line in the loader:

```
"\n\n".join(paragraphs)
```

`split_recursive` tries `"\n\n\n"`, then `"\n\n"`, then `"\n"`, then `" "`. A
blank line between paragraphs makes the **default** splitter break on a
paragraph rather than mid-sentence. Good boundaries, no splitter written.

> Same shape as the XY-cut cancellation: **the design predicted a feature; the
> real files said it would never fire.** `.docx` is in `LOADERS` and
> deliberately **not** in `SPLITTERS`.


### The one thing the loader must get right: runs

Word splits a sentence across runs whenever formatting changes. Measured on the
committed fixture:

```
"X_test, X_train, Y_test, Y_train = train_test_split (X,Y, test_size = 40% )"
   -> 15 separate <w:t> runs

one paragraph begins with the runs   "T"   then   "his paper"
```

Per document, paragraphs split across runs: **105, 88, 77, 75, 57, 50, 38, 30,
24, 1, 0 …**

**Join runs with `""` and paragraphs with `"\n\n"`.** Join runs with a space
and `This paper` becomes `T his paper` — the same family as the notebook
`_join` bug, where nbformat already carries the newline.

`<w:tab/>` becomes a tab and `<w:br/>` a newline, so two table cells never fuse
into `NameValue`.


### A new attack surface: the .docx zip bomb

`sources/archive.py` guards an uploaded `.zip`. **A `.docx` is a ZIP arriving
through a different door**, and `ZipFile.read` decompresses fully into memory.

```
real papers        44KB compressed -> 266KB   (ratios 5-14x)
a crafted archive  48KB compressed ->  50MB   (ratio 1028x)
```

`MAX_DOCX_XML_BYTES = 10_000_000`, checked against `ZipInfo.file_size`, which
comes from the **header** — so the size is known before a byte is decompressed.
37x the largest real file, and fatal payloads are refused.

> **Every new format is a new door. Ask which guard the other doors already have
> that this one does not.**


### The three refusals, all measured

| guard | catches |
|---|---|
| `zipfile.BadZipFile` | empty, plain text, PNG, PDF, truncated — all five raise it |
| `KeyError` on `word/document.xml` | a ZIP that is some other Office file |
| `ET.ParseError` | broken XML |

No density or vowel guard is needed. A `.docx` with no text returns `""`, and
`chunk_bytes` then yields nothing, which the API already answers as a **422
`empty_artifact`**. The failure is already loud.


### A tab is kept, not converted to a space

The first version turned `<w:tab/>` into a space, reasoning that
`split_recursive`'s ladder ends at `" "` and has no `"\t"`, so a long
tab-separated row would have no break point. Measured on the real paper:

```
tabbed paragraphs                 16
tabbed paragraphs over the cap     0
longest paragraph   1821 chars, 300 spaces
```

The danger never materialises, and a tab keeps table columns visible. The test
was renamed with it — the old name promised a space the code did not produce.


### Mutation results — eight, all caught

| mutation | fired |
|---|---|
| join runs with a space | 3 tests, incl. the `T his paper` one |
| join paragraphs with one `\n` | the blank-line test, alone |
| no bomb guard | the bomb test, alone |
| drop the tab | the tab test, alone |
| stop catching a missing `word/document.xml` | the not-a-Word-file test, alone |
| stop catching broken XML | the broken-XML test, alone |
| remove `.docx` from `LOADERS` | the registry test, alone |
| remove `.docx` from `READABLE_SUFFIXES` | `test_every_format_we_can_read_is_also_a_format_we_can_fetch` |

**Two things the process caught that reading could not.**

`ET.ParseError` is a **subclass of `SyntaxError`**, so the first
"stop catching broken XML" mutation still caught the error and looked like a
dead test. It was the *mutation* that was broken.

> **"A mutation survived" is not a verdict either.** Prove the mutation actually
> changed behaviour before blaming the test.

And every `.docx` test called `load_docx` **directly**, so removing the suffix
from `LOADERS` broke nothing — **nothing proved the loader was wired in at
all**. `test_a_word_paper_becomes_chunks_through_the_registry` goes through
`chunk_bytes` and now fires alone.


### The review pass — two rules that were prose and nothing else

Asking *which real failure is still unprotected?* across the whole project
found two load-bearing rules with no test behind them. Both are cheap, both
were mutation-verified, and both fire alone.

**`test_no_runtime_requirement_would_blow_the_memory_budget`.** This file has
said since 2026-08-11 that installing `torch` is *"the single decision that
would end the free tier instantly"* — 300-500MB resident against a hard 512MB
ceiling that ingest and the API share. Nothing checked it. `requirements.txt`
could have gained `torch` and CI would have stayed green. Runtime only:
`requirements-dev.txt` may hold heavy packages, because the local ONNX reranker
is deliberately a dev dependency that never ships.

**`test_every_committed_fixture_names_its_source_and_its_licence`.** Slice 3
added 4.7MB of third-party binaries — three arXiv PDFs and a CC-BY Word paper.
`data/samples/SOURCES.md` now records source and licence for each, and this
test fails the build if a binary is committed without provenance. Git history is
permanent; a fixture nobody can trace cannot be audited or removed.

> **A rule written in a document is a rule that will be broken.** Both of these
> had been true and unenforced for weeks.


### What `.docx` deliberately did NOT get

No API test and no repository-walk test. Both would be one test per
**combination**: the binary-through-the-API path is already pinned by the PDF
upload test, and binary-through-the-walk by the real-paper test. Same failure,
different input.


### Honest limits

- **The tab decision rests on one paper**, not on the 24 that settled `.pdf`.
  A tab-separated row over 1530 characters with no spaces would fall to blind
  fixed-size cuts. Real in mechanism, absent in this population.
- **`.doc` (the old binary format) is not supported** and is not in
  `READABLE_SUFFIXES`. It is not a ZIP, so it refuses loudly.
- Tables arrive as one paragraph per cell, which reads as a vertical list.
