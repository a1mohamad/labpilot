# Full text: Slice 5 — DONE 2026-08-17

[Docs home](../../README.md)

## Slice 5 — DONE 2026-08-17

**The last box of the walking skeleton. One compare endpoint over the pipeline
that already worked.** It took one short session, as predicted — FastAPI is on
the assumed-known list, so the work was all in a handful of decisions.

It shipped as one `app.py`, and was **restructured the same day** — see
[the API layout](../../step0/slice-5-and-the-api.md#the-api-layout--restructured-2026-08-17). The decisions below
survived the restructure unchanged; only their addresses moved.

**The request is `multipart/form-data`** — two named `UploadFile` parameters `a`
and `b`, plus `question` as a form field. Two *named* parameters rather than a
list, because the side is then the parameter name and no `side` field is needed.
That matches the two named slots in [the UI shape](../../product/ui.md#ui-shape--step-3-recorded-now).

**The response carries what this file already required**, not what was
convenient: `model` / `tier` / `attempts` because
[the `LLMResult` rule](../../llm/chains.md#llm-serving--fallback-chain) says the user must see which
tier answered, `chunks` per side because `✓ 42 chunks` is what proves the file
was really read, `finish_reason` because `MAX_TOKENS` means the report is cut and
looks complete otherwise, and **the resolved citation list** — `source`, `line`,
`text`, `unique` — because that is the one thing an endpoint adds over a print
statement.


### The four decisions worth keeping

**1. The route is `def`, not `async def`.** Our transport is `requests`, which
blocks. Inside `async def` a blocking call freezes the event loop and the server
stops answering *everyone*; a plain `def` runs in a thread pool. This is a slice
1 choice (`requests` for every tier) reaching forward into slice 5, and it is
also why the body uses `upload.file.read()` and not `await upload.read()`.

> **The transport you chose at the bottom decides the concurrency model at the
> top.** Nothing warns you — the async version works perfectly under one user.

**2. HTTP status codes are the API-layer form of an existing rule.** CLAUDE.md
already says *"a caller's bug and a provider's failure are different
exceptions."* This is where that becomes visible outside the process:

| Raised | Status |
|---|---|
| `ValueError`, bad decode, missing extension, empty artifact, blank question | **422** |
| upload over `MAX_UPLOAD_BYTES` | **413** |
| `AllFreeTiersExhausted` | **503**, with the `attempts` list in the body |

`LLMError` needs no branch — the fallback loop swallows it and it never escapes
`LLMClient`. A prompt too large for every tier also arrives as
`AllFreeTiersExhausted`, so 503 covers it honestly.

**3. A missing file extension is a 422, not a default.** `chunk_bytes` picks its
splitter from the suffix. Without one it falls back to recursive splitting — no
AST boundaries, no function units, a quietly worse comparison, **and no error**.
This is the [orphan-chunk failure](../../retrieval/chunking.md#five-failure-modes-to-test-against) arriving
through the front door.

> **Refuse the input you cannot handle well. A silent downgrade is worse than a
> rejection, because nobody ever learns it happened.**

**4. Size is checked against `upload.size` *before* the bytes are read.**
Starlette knows the size once parsing finishes, so reading a 200MB upload merely
to measure it would spend 200MB on a **512MB** box — see
[the memory budget](../../product/memory-budget.md#memory-budget--render-free-tier-512mb). The post-read check
stays as a backstop for the case where `size` is `None`. 1MB is not a new number:
it is [the repo-walk limit](../../product/reading-a-repository.md#reading-a-repository--step-1-recorded-2026-08-11)
applied at a different door.


### Two dependencies, and one of them is runtime

| Package | File | Why |
|---|---|---|
| **`python-multipart==0.0.32`** | **`requirements.txt`** | FastAPI cannot parse a form without it, and it is **not** a FastAPI dependency by default |
| `httpx2==2.10.0` | `requirements-dev.txt` | `TestClient` needs it. Plain `httpx` works but Starlette 1.4.1 deprecates it and warns on every run |

`fastapi` and `uvicorn` were already pinned — installed in Step 0 and unused
until now. Pydantic 2.13.4 arrives with FastAPI, so the response models cost no
new line.


### `integration/` did NOT become real, and the reason is the cost rule

The obvious reading is that an endpoint over four packages is an integration
test. **In this repo it is not**, because
[the folders split by cost](../../development/architecture-layers.md#layout--plan-the-shape-early-create-files-late), not
by how many layers a test touches:

| Folder | Means | Real yet? |
|---|---|---|
| `unit/` | no network, no database | yes |
| **`api/`** | **`TestClient`, no network — runs by default** | **now** |
| `integration/` | **real Supabase / real pgvector** | **Step 1** |
| `smoke/` | spends API quota, opt-in only | yes |

So the *textbook* integration test lives in `api/`:
`test_the_real_sample_pair_flows_through_the_endpoint` uploads the actual
`A_paper.md` and `B_train.py`, mocks only `LLMClient`, and asserts the chunk
counts match `chunk_file`, that side B was genuinely trimmed (`sent < total`, so
selection really ran), and that the prompt fits `PROMPT_BUDGET`. Real chunking,
real selection, real prompt building, over real HTTP, **at zero quota cost**.

**No API smoke test was added, deliberately.** `tests/smoke/test_pipeline_answers.py`
already proves the pipeline answers, and the HTTP layer touches no provider — a
weekly request would buy nothing. *"Do not add tests to raise a number"* applies
to smoke tests hardest, because those ones cost quota.


### Hardening, and what running it for real exposed — 2026-08-17

**Starting the server by hand found three things no test could.** Every one was
invisible to a green suite, which is the point.

**1. The app never loaded `.env`, so it could not work once.** `LLMClient` reads
keys from `os.environ` at call time, and only the *smoke tests* called
`load_dotenv()`. `uvicorn labpilot.api:app` therefore started with no
credentials: all 15 tiers failed on "key is not set" and the endpoint answered
**503 — identical to a total provider outage.**

**No API test could catch it, by construction**, because they all override the
`LLMClient` dependency and never read a key. `tests/api/test_app_startup.py` now
closes it with a **subprocess**: a fresh interpreter, `GOOGLE_API_KEY` stripped
from its environment, must still find the key after importing the app. A second
test pins the opposite direction — a platform-supplied variable must **win** over
`.env`, or a deployed server would read a stale committed value.

> **A dependency override is a hole in your coverage, not just a convenience.**
> Whatever it replaces is untested. List those things and test them another way.

**2. A legal upload could send a prompt with no evidence in it.** Measured: 875KB
of Python — comfortably under `MAX_UPLOAD_BYTES` — is **8,334 parts**, whose
outline alone costs **210,541 tokens of a 26,000 budget**. `select()` then
returns nothing and the prompt is **185,640 tokens of headers**. Gemini's 1M
context means it would be *sent*, spending a scarce request to ask a model about
a list of filenames.

This is [the outline scaling problem](../../prompts/comparison-template.md#the-outline-does-not-scale-past-step-0)
that this file already recorded for Step 1 — **the endpoint simply made it
reachable, and nobody had guarded the door.** `services._prompt` refuses with a **413**
naming the real numbers. The fix is a guard, not a redesign: Step 1 still has to
replace the per-chunk outline with a per-file one.

> **Recording a limit is not the same as enforcing it.** Every "this does not
> scale past Step 0" note is a missing guard until something checks it.

**3. `thinking=HIGH` and the 180s read timeout were still live.** Both were
written down as owed and neither had been applied. Fixed, and the live run
confirms the measurement: **`MEDIUM` returned a complete report — `STOP`, 11,507
characters, 47 of 47 citations resolved — in 52.7 seconds.**

**And 52.7s is worth reading honestly: the timeout raise was not what fixed it.**
The old 180s limit would have been fine. `MEDIUM` is simply far cheaper than
`HIGH`, which is very likely the real cause of the timeouts session 10 blamed on
the timeout value. **Two changes shipped together; only one did the work.**

#### `integration/` became real, with a wider definition

It was defined as *"real Supabase / real pgvector"*, which cannot exist until
Step 1. But a genuine gap had opened between the layers:

| Suite | Mocks | So it never exercises |
|---|---|---|
| `unit/llm/` | providers, at the `Provider` protocol | HTTP |
| `api/` | the whole `LLMClient` | the chain |

**Nothing joined them**, and the five-way failure rule only matters if its
verdict survives into an HTTP response body. `tests/integration/` now runs
API → pipeline → `LLMClient` → chain → **real provider HTTP mocked with
`responses`** — free, no quota, and it pins that a 503 is retried on the same
tier, that a spent pool skips its sibling **without spending a request**, that an
oversized prompt costs its tier nothing, and that a total failure reaches the
client as a 503 naming every tier.

The folder definition is widened to **"several real layers, mocked only at the
outer edge"**. Step 1's pgvector tests fit that unchanged; today's fit it too.

#### One smoke gap, and it was the template we actually ship

The weekly run exercised `FULL` and `CORE` — both **frozen baselines we no longer
use** — while **`REPORT`, the template the endpoint sends, had no live test at
all.** `RUNS` now includes `(REPORT, True)`. Stuffed, so retrieval is not a
variable and the score is comparable with the saved baselines — which also makes
the weekly run produce, by itself, the measurement **START HERE** lists as owed.

**No API smoke test was added.** It would cost a request a week to prove what
`test_pipeline_answers.py` already proves, and the one bug it would have
caught — the missing `load_dotenv()` — is now covered for free by the subprocess
test. *"Do not add tests to raise a number"* binds hardest where the number costs
quota.

#### `.env.example` was quietly lying

It still said Google gives **"~1,500 requests/day"** — the exact fiction session 9
overturned — and its tier numbers were from the seven-tier era, when `glm-5-2`
was tier 2 and is now dead. The existing test only checks each variable
**exists**, never that the comment beside it is true.

**Every tier number is now gone from that file**, replaced by model names, per
this file's own rule: *"Route by model name, never by tier index."* A number that
goes stale twice in one day should not be written down a third time.

> **Untested prose rots faster than untested code**, because nothing ever fails
> when it goes wrong. The fix is not more tests — it is writing down the fact
> that does not change (a model name) instead of the one that does (its rank).


### The test that could not fail — 2026-08-17

Every new invariant was broken on purpose to check its test noticed. Four of five
did. **The size-limit test passed against a build with the limit raised 100×:**

```python
huge = b"x = 1\n" * (MAX_UPLOAD_BYTES // 3)  # ← the bug
```

The payload size was derived from **the constant under test**. Raise the limit
and the payload grows with it, so the assertion could never fail. The 413 was
genuinely ours and the test was green for three runs — it was simply not testing
anything. Fixed with a **fixed literal** payload plus an explicit premise
assertion (`assert len(huge) > MAX_UPLOAD_BYTES`) so the test fails loudly if the
limit is ever raised past it, and a companion test pins the accepting side so the
limit cannot silently drift to zero either.

> **A test whose input is computed from the value it is checking cannot fail.
> Every threshold test needs a literal on one side of the comparison.**

This is [rule 7](../../step0/prompt-experiments.md#prompt-design-rules-earned-2026-08-17) — *grade content, never
shape* — in its test-suite form, and the same mistake as *"the walks ran"* in
session 9: a green signal was read without asking which cases produce it.
**Mutation testing is the cheap fix, and it took one loop of five `sed`
replacements.** Do it for every invariant this file claims to pin.


### What slice 5 deliberately did not do

Both are recorded rather than solved, and both belong to Step 3:

- **The endpoint is synchronous.** A report can take minutes against
  `DEFAULT_TOTAL_BUDGET = 900 s`; any proxy will kill it, Render especially. SSE
  is already scheduled — see
  [live progress events](../../llm/reranker-chain.md#chain-3--reranker-true-fallback).
- **The per-file cap is enforced after Starlette has spooled the upload to disk.**
  The whole-body cap is now checked *before* parsing (see the restructure below),
  but a true streaming limit still belongs in nginx.

~~No `/health` endpoint yet.~~ **Added in the restructure**, because the moment
the server is started by hand there is something to probe.
