# Full text: The page and the container — 2026-08-17

[Docs home](../../README.md)

## The page and the container — 2026-08-17

*Deliberately small, and deliberately throwaway. The real UI is Step 3.*

| Path | Holds |
|---|---|
| `web/index.html` · `styles.css` · `app.js` | one static page, **no build step, no `node_modules`** |
| `docker/Dockerfile` | `python:3.13-slim`, non-root, `HEALTHCHECK` on `/health` |
| `.dockerignore` | never ships `.env`, `tests/`, `data/`, `artifacts/` |

> **REBUILT 2026-09-15 for the two doors, and given a visual pass. The table
> above still describes the FILES; what the page DOES changed - see
> START HERE.** It had posted two files to
> `/compare` since that endpoint took ids, so it had been broken since slice 7.

**Why plain HTML and not TypeScript yet.** The rewrite risk lives in **state**,
not in the framework. A TS app that manages sessions, artifact slots and chat
history must be rebuilt once Step 1 gives artifacts a real identity. A page that
posts a form and prints the answer has almost no state to invalidate — throw away
100 lines, not an app.

**That argument was re-checked on 2026-09-15 and STILL HOLDS, for a different
half.** Artifacts now DO have a real identity, so the original precondition is
met - but the state a typed app would model is sessions, chat history, SSE
progress and the 0/1/2-artifact modes, and every one of those is **Step 2** work
that does not exist yet. So TypeScript stays a Step 3 job: typing state before
it settles is the same rewrite-twice trap, one step later.

**The page obeys the rules this file already set** for
[the UI shape](../../product/ui.md#ui-shape--step-3-recorded-now): two **named** slots, the question
box **prefilled and editable** (never a placeholder, because that text is also
the retrieval query), `n/m chunks` per side, the model and tier that answered,
and every citation as `B_train.py:1203` with `(not unique)` marked. `MAX_TOKENS`
and any failed tier render as **warnings** — a truncated report otherwise looks
complete.

**Served from the same origin at `/ui`**, which is why `CORS_ALLOW_ORIGINS` can
stay empty. The mount is conditional, so an API-only deployment simply does not
ship `web/`.

Four deliberate choices in the Dockerfile:

- **`.env` is never copied.** Keys come from the platform, and `load_dotenv` does
  not override what the environment already supplies.
- **Runs as a non-root user.**
- **`HEALTHCHECK` hits `/health`** — the endpoint added in the restructure.
- **One worker.** Every extra worker is a full interpreter copy against a
  [512MB ceiling](../../product/memory-budget.md#memory-budget--render-free-tier-512mb), and the route is a
  plain `def`, so uvicorn's thread pool already serves concurrent requests.

**Not verified: `docker build` has never been run.** The file is straightforward,
but unbuilt is unverified — treat it as a draft until an image exists.

**Still unsolved, and it is the reason the real UI waits:** a report takes ~53
seconds and the page can only show a spinner. Live tier-by-tier progress needs
**SSE**, which is Step 3.

### Step 0, honestly closed

| Slice | Shipped |
|---|---|
| 1 | tier 1 returns text |
| 2 | the fallback chain, now 15 tiers and a five-way failure rule |
| 3 | the chunker (permanent) and the dumb selector (throwaway) |
| 4 | the prompt — 13 of 19 findings, ~99% citations, correct conclusion |
| 5 | **`POST /api/v1/compare`** |
| *after* | the API restructure · the system-wide audit · a static page and a Dockerfile |

> ### STEP 0 IS COMPLETE — 2026-08-17
>
> All five slices shipped, and a real HTTP request now runs the whole pipeline
> end to end: upload → chunk → select → prompt → `LLMClient` → an answer whose
> citations resolve to real file and line numbers. **Proven live over uvicorn
> against a real model**: `gemini-3.6-flash` at tier 2 after tier 1 returned 503,
> `finish_reason: STOP`, 11,507 characters, **47 of 47 citations resolved**, in
> 52.7 seconds.
>
> **284 tests — 210 unit, 49 api, 6 integration, 19 smoke — ruff clean.**

**What Step 0 proved:** the core idea produces something useful, and every layer
connects. **What it did not prove:** that it works on anything but one fixture.
`quora_siamese` is a single pair, in one domain, in one language. A second pair
is the only way to tell a general system from a quora-shaped one, and it belongs
in Step 1.

**The layer-balance rule is satisfied again.** The prompt layer raced far ahead
during slice 4; slice 5 brought the API up from nothing. Step 1 must now do the
same for retrieval, which is still a hardcoded 50/50 positional split.
