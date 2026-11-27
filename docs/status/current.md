# Current status

[Docs home](../README.md)

**2026-11-24. Steps 0 and 1 are done. Step 2 (the agent): slices 0 to 11 are DONE. Next: slice 12,
the size gate and big repositories → [the brief](../step2/slice-12-brief.md).**

**UPDATE 2026-11-27:** the problems of slice 12 are listed [below](#slice-12-the-problem-list-2026-11-27) (S12-1 to
S12-20). No design is chosen and no code is written. `main` was at `a0d921d` with a green CI before this docs change.

| | |
|---|---|
| branch | slice 11, the cleanup and the CI fixes are on `main` (`461eb2a`, its CI is green) and on `feat/routing`. Slice 12 needs a NEW branch from `main`: ask first |
| last tests by Claude | unit and api: 2,677 passed, 5 skipped, and 60 related database tests passed (2026-11-24, after the cleanup). The FULL suite is run by the user |
| cleanup | dead code out, repeats in one place, claims list whole (D140 to D142, M35), and CI green again → [34](../step2/34-cleanup-before-slice-12.md) |
| closed last | slice 11, routing → [33.8](../step2/33-slice-11-routing.md#338-slice-11-is-closed-the-last-work-and-the-closing-review--2026-11-24) |

## The flow of one question today

1. Rewrite a follow-up. Then the planner, beside the two stored summaries. Then the gate.
2. Everything fits the prompt: read it whole. If not: one search per query at the same time, merge, one rerank per side.
3. `extract_claims`, then `find_differences` and `find_bugs` at the same time, then one final merge. Saved results are read, not made again.
4. `respond` (it may first ask the user one question), then the chat is saved.

Every model call walks the route of its own task: quick and nearly-as-good models first, a second
model beside a late one (the race), a memory of failed models, a full room or busy account skipped.

## Slice 12: the problem list (2026-11-27)

*Made with the user, one problem at a time, to refer to by number (S12-1 ...) while solving. Read from the code and
the older notes; **no model was run and nothing here is tested on a big repository**. "Big" means the total tokens of
one side (A or B), in one file or many. The plan of the work is in [the brief](../step2/slice-12-brief.md). The list may be incomplete.*

**Before any fix**

| # | problem |
|---|---|
| S12-1 | There is no test pair with a big repository and no answer key for one |
| S12-2 | There is no shared size check in tokens (D43): each step has its own limit |

**What LabPilot reads**

| # | problem |
|---|---|
| S12-3 | **Summary:** only the first 12,000 tokens, in stored order. The gate reads only the summaries (a wrong halt on a big repository is a guess) |
| S12-4 | **Claims:** A over 28,000 tokens (`CLAIMS_BUDGET`) gets none, and the user is not told, only the server log. For a big A we must choose which parts are read and how many claims are kept, because each claim also costs audit calls (D140). The group size is open (M27) |
| S12-5 | **No differences at all** when A is over 28,000: there are no claims, A is also over the 20,000 the scan can read as text, so the audit and the scan both do not run |
| S12-6 | **B is read up to 40,000 tokens** (audit, scan, bug hunt, fresh check): whole files in stored order, not chosen by the question. A large file that does not fit can be skipped completely. Only the server log says so |

**Wrong or missed findings**

| # | problem |
|---|---|
| S12-7 | **Audit, unread files:** it can say "B is missing this" when an unread file has it. The prompt does not say that B is partial, and the judge reads the same part of B |
| S12-8 | **Audit, pieces of B:** in one vote "same" in any piece wins, so a "differs" is dropped when two places in B disagree and sit in two pieces. If the call with the right piece fails, a false "missing" can stay. The user's view: real, but not a big problem |
| S12-9 | **Scan, a big A:** over 20,000 it gets only the list of claims, which is not all of A, so it can say "A never says this" when A does. The judge gets the same list |
| S12-10 | **Scan, unread files:** it says nothing about them. A guess: on a big repository it may also give many small findings that take the room of important ones |
| S12-11 | **A model decides without seeing the proof** (one root, the user's point, with two places to fix). (a) Finding suspects: each piece of B answers the checklist alone, one "no" with a quote makes a suspect, and a "yes" from another piece is not used; trace reads small pieces, so it can also miss a bug that needs two files. (b) Judging: when the B that was read is over 30,000, the skeptic sees only the parts the suspects point at; a concept suspect goes only when both votes say "false" (or "repeat"). Fixing (a) alone does not fix (b) |
| S12-12 | **A weak checklist:** it is written from the summary (S12-3) and the part headers of the B that was read, cut at 6,000 characters |

**Cost**

| # | problem |
|---|---|
| S12-13 | **More B means many more calls.** Estimates by arithmetic: audit = claim batches (30) x pieces of B (about 24,000) x 2 votes; the scan sends A again with each 2,000-token piece (A 20,000 and B 40,000: about 440,000 input tokens); the bug hunt makes about 28 calls before the skeptic for 40,000 of B and about 126 for 200,000. Each judge call gets all the B that was read, but its route is sized for a 12,000-token prompt (`TASKS` in `llm/routes.py`) |

**What is searched, kept and saved**

| # | problem |
|---|---|
| S12-14 | **Search:** the planner map is cut at 12,000 tokens and `file_scores` is not given to it; at most 6 planner queries; the rerank window, rerank at all and a cap on the parts list are not tested on a big B ([26.9](../step2/26-slice-7-built.md)) |
| S12-15 | **Final prompt (30,000):** nothing makes sure the important parts stay (M34, [29.14](../step2/29b-slice-9-followups.md)) |
| S12-16 | **Finding lines:** at most 25% of the prompt, in a fixed order that does not look at the question (M32, [29.13](../step2/29b-slice-9-followups.md)) |
| S12-17 | **Saved results, the name:** it does not say which parts of B were read. Correct today (the same files every time); wrong once files are chosen by the question. **Idea of the user, Claude agrees, not built:** put the parts that were read in the name, as a hash; choose the files BEFORE the saved result is looked up; change `with_saved_steps` too. The cost: a different set of files is checked again |
| S12-18 | **Saved results, incomplete:** when some model calls fail, what came back is still saved and used again (claims with missing groups; differences when only the audit or only the scan answered; bugs when only some questions answered). **It can happen today.** S12-17 does not fix it |

**Other**

| # | problem |
|---|---|
| S12-19 | **Upload of a big repository:** the time, the embedding quota and the database space were not checked. Size limits exist in the code |
| S12-20 | **Limits for every fix:** free quotas (Gemma 16,000 input tokens a minute for each key and model, LiteRouter one call at a time), the answer time (the goal is 4 to 5 minutes, not proven), 512 MB of memory, 500 MB of database |

UPDATE 2026-11-27 to the brief: its job 10 names `FileFacts.expand`, but no Python file has `FileFacts` now, so that
job looks outdated. The brief itself is not changed yet. Also still in the brief and not discussed on this day: M13 and
M14, the audit answer "I need more context", and the rerun of `run_r23.py`.

## Open now

- **Proof of speed:** a first answer on two files took 219 to 275 s with quotas and 248 to 330 s with most
  daily quotas spent; "always under 5 minutes" is NOT proven. Two runs on fresh quotas are owed (otp, quora).
- **`method` and `concept` have one good model** (DeepSeek V4.1 Flash). Ling, MiniMax M3.1 and Gemini 4 Hydrogen
  are not really measured there.
- **Live check of streaming** for Gemini 4 Hydrogen, Token Harbor and Cloudflare; one weekly smoke run.
- The **fast mode** of `find_bugs` is built and NOT measured.
- **The weekly Smoke run is red** and three database tests failed once with no known reason ([34](../step2/34-cleanup-before-slice-12.md#ci-after-the-merge-2026-11-24-to-26)).
- The next free numbers are **D143** and **M36**.
- **At the end of Step 2: make citations much better** (the user's plan), with the check that refuses an answer whose
  citations cannot be resolved ([29.20](../step2/29b-slice-9-followups.md)). Commit `63a0381` on `feat/agent-nodes` holds the old reminder.
- Slice 13 measures everything on many pairs ([27.1 and 27.2](../step2/27-slice-7-decisions-and-slice-13.md), [33.5](../step2/33-slice-11-routing.md)); slice 14 tries Jev.

## The slices of Step 2

0-11 done. **12** big repositories (next) · **13** measure, tune, generalize · **14** Jev for decisions ·
then the citations work, Step 2.5 (web search, MCP), Step 3 (deployment, UI), Step 4 (fine-tuning).
The table with the story of each slice: [Step 2 progress](step2-progress.md). Older notes: [history](history.md).
