# Slice 12 brief: the size gate and big repositories

[Docs home](../README.md)

*Updated 2026-11-24 after the cleanup ([34](34-cleanup-before-slice-12.md)). Written 2026-11-24 from the older notes. Nothing of slice 12 is built. The plan says 2 lessons, maybe more
([the slice table](00-plan.md)).*

## The goal

LabPilot must work well when A or B (or both) is a big repository. Today a big file is read only in part:
the first parts that fit (the summary), 40,000 tokens (`find_bugs`, `find_differences`), 28,000 (claims), and
about 60 parts of the search reach the answer.

## First job: a test pair

**There is no pair with a big repository.** It is built BEFORE the design, with an answer key written before any run
and never read while tuning ([18.3](18-big-repository.md), [27.1](27-slice-7-decisions-and-slice-13.md)). Then the loss is
measured before any fix.

## The work

| # | job | where the plan is |
|---|---|---|
| 1 | one `fits(side, budget)` check in TOKENS, used by claims, the outline, the bug hunt and the summary (D43, CC10) | [21.2](21-final-design.md) |
| 2 | claims of a big A: rank the files, take files up to a total budget, parts of one fixed size, a round-robin join, a cut (D26 to D28, D68, D69). **Claims use groups of about 2K, not 12K** (25.2); the group size is open (M27) | [18](18-big-repository.md), [23](23-slice-7-design.md), [25](25-slice-7-measurements.md) |
| 2b | **the limit of the claims of a big A** (D140, 2026-11-24): the old 48 is gone and the list is whole, so otp gives 102 to 132 method claims, which is 4 to 5 audit batches of 30, 2 votes each, for every group of B. Choose the limit HERE, with M12 and M13, and choose WHAT is cut (a claim is a fact the audit may need) | [34](34-cleanup-before-slice-12.md) |
| 3 | the good summary of a big artifact (D46, M14). It replaces the stored simple one: raise `SUMMARY_VERSION` | [21.2](21-final-design.md), [31.16](31b-slice-10-built.md) |
| 4 | the scan and the hunt of a big B: the 40,000-token limit, how files are chosen (by the question and `file_scores`, not by name), what the user is told ("12 of 161 files read") | [29.8](29a-slice-9-findings.md) |
| 5 | keep the most important parts when B is cut: M34 first (the loss), then candidates K1 to K8 | [29.14](29b-slice-9-followups.md) |
| 6 | rank the finding lines against the question (M32) | [29.13](29b-slice-9-followups.md) |
| 7 | extend the saved results of D104 to big repositories | [29.10](29b-slice-9-followups.md) |
| 8 | re-run `run_r23.py` on a big B: the rerank window, rerank at all, a cap on the parts list | [26.4, 26.9](26-slice-7-built.md) |
| 9 | an audit answer "I need more context" with a search (improvement 5) | [29.9](29a-slice-9-findings.md) |
| 10 | `FileFacts.expand` recomputes the whole file at each check: check its time on a big B | [26.11](26-slice-7-built.md) |

Linked size limits that must be designed together: `CLAIMS_BUDGET` (28,000), `A_WHOLE_TOKENS` (10,000) and the A text
of the scan (20,000) ([27.1](27-slice-7-decisions-and-slice-13.md)).

## Limits to respect

Gemma 16K input tokens a minute for each key and model; LiteRouter one call at a time; the answer time (the goal is
4 to 5 minutes, so more calls must run together); 512 MB of memory (stream, never hold the repository);
500 MB in the database; the routes ([33](33-slice-11-routing.md)): a task with a bigger prompt needs its numbers in
`TASKS` (`labpilot/llm/routes.py`) changed, and `tests/unit/llm/test_routes.py` with them.

## Measurements owed here

M12 (files taken, claims kept, gate numbers), M13 (claim ranking), M14 (the summary designs), M27 (the group size),
M32 (ranking the findings), M34 (the loss of the cut). The new pair also serves slice 13 (M5, M18 and the rest).
