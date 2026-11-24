# Git state and branches

*UPDATE 2026-11-24: slice 11, the docs split and the cleanup are on `main` (`c4eb693`, from `99f4dc6` with 313 one-file commits by `merge_per_file.py`) and on `feat/routing` (`125e54e`); `git diff main feat/routing` was empty right after the merge. The notes below are older.*

[Docs home](../README.md)

### Git state and branches

As of 2026-10-19 slice 4 is on `feat/planner` (pushed) and on `main` (pushed), at the user's explicit request: ONE commit
on `feat/planner` that holds the lesson 5 map work and the closing review, and `main` received every file of slice 4 as its
own commit (the same content, different hashes). Slice 3 and the split of `api/services.py` were already on `main`.
`feat/agent-nodes` (`b72955a`, also on origin) is kept, not deleted. It holds the row level security work as ONE commit
where `main` has it as five (17.15). **It also holds a docs commit that `main` does NOT have: `63a0381`, the reminder that
better citations are owed at the end of Step 2 (a short note in "Where Step 2 stands" and a longer one in the nine slices,
in both files). Bring it to `main`, or write it again.** A new branch always needs the user's permission. **Only the user
commits to `main`** (or says "merge and commit"; on 2026-10-14 and on 2026-10-19 they said so for one task each). **Dead
branches — never resume there:** `feat/reranking` (it holds an OLDER `test_llm_layer.py` that hardcodes key names),
`feat/selector` (an older squashed variant; the work lives on `main`, re-committed piece by piece), and `feat/jev-probe`
(byte-identical to `main`). This project re-commits work onto `main` piece by piece instead of merging, so hashes differ
while the content is the same. The branches of finished slices (`feat/parallel-nodes`, `refactor/split-services`,
`feat/planner`) are kept. **Slice 5 is on `feat/plan-to-run`** (made by the user from `main` at `0ac80d4`). It holds the toy file of lesson 1 (`00cb059`), lessons 2 and 3 as the user's commits `3a46eb3` to `839ca21`, and the move to `search_one` only, the closing review and these docs as commits made by Claude on 2026-10-21 at the user's request (commit to this branch only, nothing on `main`). Whether the branch is pushed was not checked. Claude suggested a NEW branch from `main` and not `feat/planner`, because `feat/planner` is 47 commits behind `main` (they split at `08a355d`) and holds slice 4 as 6 older commits. **Slice 6 is on `feat/follow-ups`** (made by the user from the tip of `feat/plan-to-run`: the user's commits `4661ea0` and `2a1d812`, a fix and tests by Claude `dbdff35` and `2bef413`, and the closing review, the door and these docs by Claude on 2026-10-22 at the user's request, pushed to `origin/feat/follow-ups`). **Slice 7, lesson 1, was typed on `feat/claims-check`** (made by the user from `main` on 2026-10-22) and re-committed on `main` one file per commit, together with the key 3 change (registry, rerank chain, embedders, `.env.example`, `smoke.yaml`, six tests), `scripts/answers/measure_claim_sizes.py`, `docs/step2/slice7/` and the docs of section 23 (the last of them `b22a40f`). **Lessons 2 and 3 are on `feat/check-claims`** (made by the user from `main`; lesson 2, its tests and the notes of D73 are ONE commit, `4c90193`; lesson 3 and section 24 are ONE commit, `bd46262`). On 2026-10-24 `main` was an ancestor of this branch and the branch was 2 commits ahead, so it can go to `main` one file per commit with `merge_per_file.py` (43 files in the dry run). That script was not in the repository then: keep a copy outside it, because it wants a clean working tree. The user commits; DETAILS.md goes before CLAUDE.md.

**2026-10-24:** slice 7 is on `main` (moved one file per commit with `merge_per_file.py`, `origin/main` equal) and on `feat/check-claims` (`d0463dd`); `git diff main feat/check-claims` is empty. The work of section 25 is in the working tree of `feat/check-claims` as documentation only; the tests and patches of 25.10 are in `artifacts/slice7-review/` and are not committed.

**2026-10-24 (late night):** 20 commits on `feat/check-claims` (9761758 to 0642da0), local only: not pushed and not on `main`. `main` is still at the state of section 25. The harness, the results and the hand-over files are in `artifacts/slice7-review/` (git-ignored).

**2026-11-15:** D110 is being built on `feat/stored-summaries` (made by the user from `feat/extract-outcomes` at `a850d48`). Nothing is committed yet. The measurement scripts are in the scratchpad and are not in the repository.
