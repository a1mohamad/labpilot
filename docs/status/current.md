# Current status

[Docs home](../README.md)

**2026-11-24. Steps 0 and 1 are done. Step 2 (the agent): slices 0 to 11 are DONE. Next: slice 12,
the size gate and big repositories → [the brief](../step2/slice-12-brief.md).**

| | |
|---|---|
| branch | `feat/routing` (last commit `d561d4a`; the slice 11 closing work and the docs split are in the working tree, NOT committed) |
| last tests by Claude | unit and api: 2,517 passed, 5 skipped (before the docs split); the related database tests passed. The FULL suite is run by the user |
| closed last | slice 11, routing → [33.8](../step2/33-slice-11-routing.md#338-slice-11-is-closed-the-last-work-and-the-closing-review--2026-11-24) |

## The flow of one question today

1. Rewrite a follow-up. Then the planner, beside the two stored summaries. Then the gate.
2. Everything fits the prompt: read it whole. If not: one search per query at the same time, merge, one rerank per side.
3. `extract_claims`, then `find_differences` and `find_bugs` at the same time, then one final merge. Saved results are read, not made again.
4. `respond` (it may first ask the user one question), then the chat is saved.

Every model call walks the route of its own task: quick and nearly-as-good models first, a second
model beside a late one (the race), a memory of failed models, a full room or busy account skipped.

## Open now

- **Proof of speed:** a first answer on two files took 219 to 275 s with quotas and 248 to 330 s with most
  daily quotas spent; "always under 5 minutes" is NOT proven. Two runs on fresh quotas are owed (otp, quora).
- **`method` and `concept` have one good model** (DeepSeek V4.1 Flash). Ling, MiniMax M3.1 and Gemini 4 Hydrogen
  are not really measured there.
- **Live check of streaming** for Gemini 4 Hydrogen, Token Harbor and Cloudflare; one weekly smoke run.
- The **fast mode** of `find_bugs` is built and NOT measured.
- **At the end of Step 2: make citations much better** (the user's plan), with the check that refuses an answer whose
  citations cannot be resolved ([29.20](../step2/29b-slice-9-followups.md)). Commit `63a0381` on `feat/agent-nodes` holds the old reminder.
- Slice 13 measures everything on many pairs ([27.1 and 27.2](../step2/27-slice-7-decisions-and-slice-13.md), [33.5](../step2/33-slice-11-routing.md)); slice 14 tries Jev.

## The slices of Step 2

0-11 done. **12** big repositories (next) · **13** measure, tune, generalize · **14** Jev for decisions ·
then the citations work, Step 2.5 (web search, MCP), Step 3 (deployment, UI), Step 4 (fine-tuning).
The table with the story of each slice: [Step 2 progress](step2-progress.md). Older notes: [history](history.md).
