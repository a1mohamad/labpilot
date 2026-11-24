# Section 18: a big repository as side A (slice 12)

[Docs home](../README.md)

### 18. SLICE 9 — a big repository as side A, decided 2026-10-07

*(Renumbered on 2026-10-14: this is slice 12 now, see [section 21](21-final-design.md#21-the-final-design-and-the-new-slice-list--agreed-2026-10-14). The heading is kept so that old links work.)*

*Talked through with the user during lesson 1. The user was confused about what a
claim is and where claims come from, and asked for the big-repository case to be
built as the LAST slice. Nothing here is built.*

#### 18.1 The project in one picture (the user asked for this reset)

A is the SOURCE: the paper, or the original code. B is what the user built. The
question LabPilot answers is: **why does B not get the results of A, and what is
different?**

```
A (source) -> extract_claims (one cheap call) -> a list of claims
              each claim = one search text
                       -> search in B -> verify -> a list of differences
                       -> explain why the results differ
```

- Claims come from **A only**. B is the thing we search in.
- **The format of A does not matter to this step.** Step 1 already turns a PDF, a
  Word file, a notebook, code and a git repository into chunks of text with a
  header, so `extract_claims` reads chunks and never sees a format.
- What really changes is **size** (does A fit one call? `measure()` says), **how
  many facts** it holds (a paper about 14, a repository hundreds), and the place
  label (a page, or a file and a function).
- With **one artifact only** there are no claims. Other tools are used: summarize,
  find bugs.
- **Withdrawn:** an idea of "roles" and a "two-way walk", and a suffix rule to
  choose the mode. It made the picture harder, and the user rejected it. Do not
  build it.

#### 18.2 Decisions

| # | decision |
|---|---|
| **D24** | `extract_claims` is ONE cheap call over A. Its **instruction is fixed and versioned**, its **output has a fixed JSON shape** (`text` plus where it was seen), the **claims are saved beside the report** (a fallback tier writes different claims), and a **short fixed list is the backup** when the call fails |
| **D25** | **The user's question goes inside the extract instruction**, for every A that fits one call. One line of text, no new design. The default question is general, so it filters almost nothing; a specific question narrows the list. Risk: a narrow question may hide a claim that explains the gap, so **M10** checks it |
| **D26** | **Claims (slice 7) only handle an A that fits one call.** If it does not fit, the program says *"A is too big, point me at a folder or a file"*. It never cuts the input silently |
| **D27** | **Slice 12 (was 9) builds the big-repository version, by the user's decision.** If A does not fit: (1) rank the files of A by closeness to the question (`file_scores()` exists), (2) take the closest files, (3) one cheap call per file, in PARALLEL, (4) join the lists and remove duplicates, (5) **rank the claims and keep the best N**. In graph words: "does it fit?" is a conditional edge and "one call per file" is the parallel part. **UPDATE 2026-10-22 (section 23): the unit of one call is a PART of ONE fixed size, 12K tokens, for every model (D68, decided by a size test of 9 models), not one file; the parts are cut from the ranked files up to a total budget (first guess 90K), run at the same time, and joined by a round-robin cut (D69).** |
| **D28** | **The claim ranking system is NOT designed yet.** The user wants a new ranking for claims. Candidates to measure: the closeness of each claim to the question (free, needs no call), a reranker tier on the claims, or asking the extract call to give each claim a score. Decide it in slice 12 with data. **UPDATE 2026-10-22 (section 23, D69): a first design exists: up to 5 claims for each part, never forced; a ROUND-ROBIN join (the best claim of each part, then the second best) cut at 20; an optional last call that sees all candidate claims, removes duplicates and ranks them; and a quote check that drops invented claims. Scores from separate parts are not comparable, so ranking happens after the join. The candidates above are still to be measured against it.** |
| **D46** | **The summary of a big artifact must be good, and slice 12 builds it** (21.2). Slice 3 builds only the simple version: the first parts that fit 12,000 tokens |

#### 18.3 What slice 12 (was 9) needs first

**A test pair with a repository on side A.** We have none: every number in this
project comes from one paper and one Python file. A design with no test data is a
guess, so the pair is built BEFORE the design, as slice 8's third corpus was.

#### 18.4 Measurements owed

| # | measure | slice |
|---|---|---|
| M10 | the question inside the extract instruction against no question: does the model still find the same differences on `quora_siamese`? **MEASURED 2026-10-24, sections 25.2 and 25.3.** | 7 |
| M11 | does the same instruction work when A is code (Python, Go) and not a paper? Nothing here is tested yet **MEASURED 2026-10-24, section 25.3.** | 7 |
| M12 | the number N (claims kept), the number of files taken and the size-gate numbers (D43), on the new pair | 12 |
| M13 | the claim ranking candidates of D28 against each other | 12 |
| M14 | the summary designs of D46 against each other on the new pair: does the summary tell what the repository does, and how many calls and seconds does it cost | 12 |
| M27 | **the group size for claims, measured for real** (added 2026-10-27, the user's call). Today's numbers cannot choose it: the same setting (wording G, groups of about 2K) gave 9.3 of 12 on 2026-10-24 and 7.7 of 12 later, so a gap under about 1.6 of 12 is noise, and groups of about 2.9K (8.3) cannot be told apart from 2K. Every claim number comes from ONE small paper (4.3K), about 3 runs a cell. Measure 2K, 4K, 6K and 8K (M20 and R24 together) on real papers of 28K to 96K tokens (the new pair of slice 12) and on the small paper again, with at least 5 runs a cell, and report the spread beside each mean, the differences found, the claims invented, and the calls and seconds. **A proposal of the user, NOT decided:** up to 28K, groups of 2K; from 28K to 96K, groups of 4K or 6K, so a big paper needs fewer calls (90K is about 45 calls at 2K, about 15 to 23 at 4K to 6K); above 96K, the big-repository plan of slice 12 (D69). M27 decides it | 12 |

#### 18.5 Tools that already exist

`measure()` (the size of A, one round trip), `file_scores()` (files ranked by
closeness to a question), `read_headers()` and `build_map()` (the planner's map).
No new store code should be needed for D27.
