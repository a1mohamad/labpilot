# Step 0, slice 5, the API and the audit

[Docs home](../README.md)

## Slice 5 — DONE 2026-08-17

**The last box of the walking skeleton: one compare endpoint over the pipeline that already worked.** It took
one short session (FastAPI is on the assumed-known list), shipped as one `app.py`, and was **restructured the
same day** ([the API layout](#the-api-layout--restructured-2026-08-17)); the decisions below survived it.

**The request** was `multipart/form-data`: two *named* `UploadFile` parameters `a` and `b` plus `question` (the
side is the parameter name, so no `side` field is needed; it matches the two named slots in
[the UI shape](../product/ui.md#ui-shape--step-3-recorded-now)). It was replaced by ids in slice 7 (`POST /artifacts` once,
`POST /compare {a, b, question}` per turn). **The response carries what this file required:** `model` / `tier`
/ `attempts` (the `LLMResult` rule: the user must see which tier answered), `chunks` per side (`✓ 42 chunks`
proves the file was read), `finish_reason` (`MAX_TOKENS` means the report is cut and looks complete otherwise),
and the **resolved citation list** (`source`, `line`, `text`, `unique`).

### The four decisions worth keeping

1. **The route is `def`, not `async def`.** The transport is `requests`, which blocks; inside `async def` a
   blocking call freezes the event loop and the server stops answering *everyone*, while a plain `def` runs in a
   thread pool (hence `upload.file.read()`, not `await upload.read()`). **The transport chosen at the bottom
   decides the concurrency model at the top**, and nothing warns you — the async version works under one user.
2. **HTTP status codes are the API form of "a caller's bug and a provider's failure are different
   exceptions".** `ValueError`, bad decode, missing extension, empty artifact, blank question → **422**; an
   upload over `MAX_UPLOAD_BYTES` → **413**; `AllFreeTiersExhausted` → **503** with the `attempts` list in the
   body. `LLMError` needs no branch (the fallback loop swallows it); a prompt too large for every tier also
   arrives as `AllFreeTiersExhausted`.
3. **A missing file extension is a 422, not a default.** `chunk_bytes` picks its splitter from the suffix;
   without one it falls back to recursive splitting — a quietly worse comparison and **no error**.
   **Refuse the input you cannot handle well; a silent downgrade is worse than a rejection, because nobody
   ever learns it happened.**
4. **Size is checked against `upload.size` before the bytes are read** (reading a 200MB upload merely to
   measure it would spend 200MB on a 512MB box); the post-read check stays as a backstop for `size is None`.
   1MB was the repo-walk limit applied at another door (raised to 5MB for PDFs, then to 10MB on 2026-09-28).

### Two dependencies, and one of them is runtime

**`python-multipart` is a RUNTIME dependency** (`requirements.txt`): FastAPI cannot parse a form without it and
does not depend on it. `httpx2` is dev only (`TestClient` needs it; plain `httpx` works but Starlette
deprecates it and warns on every run). `fastapi` and `uvicorn` were already pinned; Pydantic arrives with
FastAPI.

### `integration/` did NOT become real, and the reason is the cost rule

The test folders split by **cost**, not by how many layers a test touches: `unit/` (no network, no database),
`api/` (`TestClient`, no network, runs by default), `integration/` (real Supabase / pgvector, from Step 1) and
`smoke/` (spends quota, opt-in). So the *textbook* integration test lives in `api/`:
`test_the_real_sample_pair_flows_through_the_endpoint` uploads the real `A_paper.md` and `B_train.py`, mocks
only `LLMClient`, and asserts chunk counts, that side B was trimmed (`sent < total`) and that the prompt fits
`PROMPT_BUDGET` — real chunking, selection and prompt building over real HTTP at zero quota cost. No API smoke
test was added: *"do not add tests to raise a number"* binds hardest where the number costs quota.

### Hardening, and what running it for real exposed — 2026-08-17

Starting the server by hand found three things no test could.

1. **The app never loaded `.env`.** `LLMClient` reads keys from `os.environ` at call time and only the smoke
   tests called `load_dotenv()`, so `uvicorn labpilot.api:app` started with no credentials: all 15 tiers failed on
   "key is not set" and the endpoint answered **503 — identical to a total provider outage.** No API test
   could catch it, because they override the `LLMClient` dependency. `tests/api/test_app_startup.py` now uses a
   **subprocess** (a fresh interpreter with `GOOGLE_API_KEY` stripped must still find the key) plus the opposite
   direction (a platform-supplied variable must **win** over `.env`). **A dependency override is a hole in your
   coverage: whatever it replaces is untested, so test it another way.**
2. **A legal upload could send a prompt with no evidence in it.** 875KB of Python is **8,334 parts**, whose
   per-chunk outline alone costs **210,541 tokens of a 26,000 budget**; `select()` returns nothing and the prompt
   is **185,640 tokens of headers**. `services._prompt` now refuses with a **413** naming the real numbers (the
   per-file outline ladder came in slice 7). **Recording a limit is not enforcing it.**
3. **`thinking=HIGH` and the 180 s read timeout were still live** though written down as owed. Fixed; the live
   run returned a complete report with `MEDIUM` (`STOP`, 11,507 characters, 47 of 47 citations, **52.7 s**). The
   timeout raise was not what fixed it — `MEDIUM` is far cheaper than `HIGH`. Two changes shipped together; only
   one did the work.

#### `integration/` became real, with a wider definition

A gap had opened between `unit/llm/` (mocks providers) and `api/` (mocks the whole `LLMClient`): nothing proved
the five-way rule's verdict survives into an HTTP body. `tests/integration/` now runs API → pipeline →
`LLMClient` → chain → **real provider HTTP mocked with `responses`** (free): a 503 is retried on the same tier,
a spent pool skips its sibling without spending a request, an oversized prompt costs its tier nothing, and a total
failure reaches the client as a 503 naming every tier. The folder definition is now **"several real layers,
mocked only at the outer edge"**.

#### One smoke gap, and it was the template we actually ship

The weekly run exercised `FULL` and `CORE` (frozen baselines) while `REPORT`, the template the endpoint sends, had
no live test. `RUNS` now includes `(REPORT, True)`, stuffed so retrieval is not a variable.

#### `.env.example` was quietly lying

It still said Google gives "~1,500 requests/day" and carried seven-tier-era tier numbers. Every tier number is
gone from that file in favour of model names (*route by model name, never by tier index*).
**Untested prose rots faster than untested code, because nothing ever fails when it goes wrong; write down the
fact that does not change (a model name), not the one that does (its rank).**

### The test that could not fail — 2026-08-17

The size-limit test passed against a build with the limit raised 100×, because its payload was
`b"x = 1\n" * (MAX_UPLOAD_BYTES // 3)` — computed from the constant under test. Fixed with a **fixed literal**
payload, an explicit premise assertion (`assert len(huge) > MAX_UPLOAD_BYTES`) and a companion test for the
accepting side. **A test whose input is computed from the value it checks cannot fail; every threshold test needs a
literal on one side of the comparison.** Same mistake as "the walks ran" in session 9: a green signal read without
asking which cases produce it. Mutation testing was the cheap fix (one loop of five `sed` replacements).

### What slice 5 deliberately did not do

The endpoint is synchronous (a report can take minutes against `DEFAULT_TOTAL_BUDGET = 900 s`; any proxy kills it,
Render especially; SSE is Step 3), and the per-file cap is enforced after Starlette spools the upload (a true
streaming limit belongs in nginx). `/health` was added in the restructure.

## The API layout — restructured 2026-08-17

*Same session, right after slice 5. **No new product decisions**; only the shape and the error body changed.* One
`app.py` held the app, route, pipeline, upload parsing and every failure branch — five reasons to change in one file,
which the layout rule forbids. The shape follows the user's own `sms-spam` and `Lung Disease Detection` FastAPI
projects: `main.py` (`create_app()` + lifespan) · `config.py` (`ApiConfig`, the project's **only** `load_dotenv`) ·
`contracts.py` (`Artifact`, `Comparison`, plain dataclasses) · `schemas.py` (wire models incl. the error envelope) ·
`errors.py` (one `ApiError` hierarchy, each subclass carrying `status` + `code`) · `error_handlers.py` (one envelope
for every failure) · `dependencies.py` (`LLMClientDep`) · `uploads.py` (the HTTP edge: `UploadFile` → `Artifact`) ·
`services.py` (the domain pipeline, **no FastAPI import at all**) · `startup.py` (`validate_provider_keys()`) ·
`routers/` (`compare.py`, `health.py`) · `middleware/` (`request_id.py`, `body_limit.py`, both **pure ASGI**). **UPDATE 2026-10-18: `services.py` no longer exists.** It was split into `ingestion.py`, `source_chunks.py`, `reading.py`, `searching.py`, `prompting.py` and `asking.py`; the map from old names to new ones is in 17.18.
**The split that carries the most weight is `services.py` having no FastAPI types:** at Step 2 LangGraph replaces
`services.py` and nothing else moves — the test of whether a seam is right. `contracts.py` and `schemas.py` are
deliberately separate (domain values change when the pipeline changes, wire models when the API changes).

### Five things that go past the reference projects

(1) `/api/v1` on `/compare` while `/` and `/health` stay off it (a probe must not know the API version); (2) failure
responses declared on the route so OpenAPI documents 413, 422 and 503; (3) the error envelope is a Pydantic model;
(4) one handler over a typed `ApiError` hierarchy (a new failure is one class); (5) the lifespan validates that at
least one chain tier has an API key — which would have caught the missing `load_dotenv` **at boot**.

### The one behaviour change

The error body moved to `{"error": {"code": "unreadable_upload", "message": "...", "request_id": "...",
"attempts": []}}` (before: `{"detail": "..."}`). `code` is stable and machine-readable, `message` is for a human,
`request_id` ties the reply to the log line, and `attempts` is filled only by `generation_unavailable`.

### Two ASGI middleware, and why not `BaseHTTPMiddleware`

Raw ASGI callables, because `BaseHTTPMiddleware` buffers the response and interacts badly with streaming and
background tasks. `RequestIDMiddleware` puts a UUID on `scope["state"]` and the `X-Request-ID` header;
`RequestBodyLimitMiddleware` refuses an oversized body by `Content-Length` *before* reading it (and counts
streamed bytes when the header is absent), the whole-body guard the per-file check cannot give. **`add_middleware`
prepends, so the LAST one added is outermost**; Request ID is added last on purpose, so a body rejected for size
still carries a correlation ID.

### What the restructure did NOT add

`app.mount(...)` was added later the same day, and `/ui` is mounted **only when the directory exists** (a mount
pointing at nothing is dead code). No docstrings: documentation is a separate later pass with the `documentarize`
skill.

### Mutation testing found the same bug twice in one day

`test_every_error_carries_a_request_id_...` passed with the middleware removed (the envelope falls back to a fresh
UUID; the middleware is pinned by `test_a_successful_response_also_carries_a_request_id`), and the body-limit test
had the same self-fulfilling shape as the upload test (`b"x" * (MAX_REQUEST_BODY_BYTES + 1)`).
**Knowing the rule does not stop you breaking it; mutation testing caught it both times, reading the test did not.**
Code state then: 210 unit, 49 api, 6 integration, 19 smoke.

## The system-wide audit — 2026-08-17

*Asked once slice 5 closed: **which real failure is still unprotected?** Four gaps; two were already broken.*

### `pydantic` and `starlette` were imported but never pinned

They arrived transitively through FastAPI, so an upgrade could move either with nothing failing (`starlette` is what
both middleware are built on). A direct import is a direct dependency. **CI cannot catch this by construction** (it
installs `requirements-dev.txt`, which pulls the whole tree), so only a test that reads the imports can.

### The API's own knobs were documented nowhere

`MAX_UPLOAD_BYTES`, `MAX_REQUEST_BODY_BYTES`, `CORS_ALLOW_ORIGINS` (later `FRONTEND_DIR`) are read by `ApiConfig`
and appeared in no template. **A knob nobody knows about is a knob nobody can turn.**

### A test of mine that lied

`test_the_documented_failures_are_the_ones_the_endpoint_can_raise` asserted `{"200","413","422","503"} <= set(responses)`
— a hardcoded set, so a new `ApiError` status would leave it green while OpenAPI misdescribed the endpoint. It now
derives the statuses from the hierarchy.

### What went in

`test_every_package_labpilot_imports_is_pinned`, `test_every_requirement_is_pinned_to_an_exact_version`,
`test_every_environment_variable_the_code_reads_is_documented`, `test_every_status_the_endpoint_can_raise_is_documented`,
`test_no_two_errors_share_a_code`, `test_the_body_limit_middleware_speaks_the_same_envelope`,
`test_an_unexpected_exception_becomes_a_500_...` — in `tests/unit/test_packaging.py` (AST-scans `labpilot/`; top of
`unit/` because it crosses every package) and `tests/api/`. **The 500 test needs a second client:** `TestClient`
re-raises server exceptions by default, so only `raise_server_exceptions=False` sees what a browser would.

### Mutation testing caught a third loose assertion

The env-var test searched the whole file text, so a name still mentioned in a **neighbour's comment** counted as
documented; it now matches a declaration line. Three in one day, all the same shape: **an assertion whose input can
satisfy it by accident.** Mutating the source caught all three; reading the tests caught none.

## The page and the container — 2026-08-17

*Deliberately small and throwaway; the real UI is Step 3.* `web/index.html` · `styles.css` · `app.js` (one static
page, **no build step, no `node_modules`**), `docker/Dockerfile` (`python:3.13-slim`, non-root, `HEALTHCHECK` on
`/health`, one worker, `.env` never copied) and `.dockerignore` (never ships `.env`, `tests/`, `data/`,
`artifacts/`). One worker because every extra worker is a full interpreter copy against the
[512MB ceiling](../product/memory-budget.md#memory-budget--render-free-tier-512mb) and the route is a plain `def` (the thread pool already
serves concurrent requests). The page is served from the same origin at `/ui`, so `CORS_ALLOW_ORIGINS` stays empty.

> **REBUILT 2026-09-15 for the two doors, with a visual pass.** It had posted two files to `/compare` since that
> endpoint took ids, so it was broken since slice 7. Each slot now uploads on its own to `POST /artifacts` and keeps
> the id; the question box sends `{a, b, question}` as JSON. It shows what the API already returned: chunk count,
> embedder, the embed-time estimate with `slow` as a warning, the artifact id, a git URL field, and `sent/total` per
> side (so a searched side reads `B: 25/1094 chunks searched`, not `25/25`). It obeys the UI-shape rules: two
> **named** slots, the question box **prefilled and editable** (that text is also the retrieval query), `n/m chunks`,
> the model and tier that answered, citations as `B_train.py:1203` with `(not unique)` marked, and `MAX_TOKENS` / failed
> tiers as **warnings**. Cards react (accent border while reading, green with a check when stored, red when refused).
> Two bugs were found by LOOKING: `#status { display: flex }` beat the `[hidden]` attribute (a display rule always
> wins, so `[hidden]` is forced off globally) and two cards sat out of line because one hint wraps. Checked in dark
> and light, at desktop and 375px, against a throwaway stub (no quota, no rows written).

**Why plain HTML and not TypeScript yet** (re-checked 2026-09-15, still holds): the rewrite risk lives in **state**,
and the state a typed app would model — sessions, chat history, SSE progress, the 0/1/2-artifact modes — is Step 2
work that does not exist yet. Typing state before it settles is the rewrite-twice trap. TypeScript stays a Step 3 job.

**The Dockerfile:** *"never built" is OUT OF DATE.* An image existed and was repaired on 2026-09-23 (the `git` layer
was missing, so the git-URL door could not work in the container; a 928-chunk ingest through it then worked) — see
section 10.3 of the Step 2 plan. Still unsolved, and the reason the real UI waits: a report takes minutes and the page
can only show a spinner; live progress needs **SSE** (Step 3).

### Step 0, honestly closed

> ### STEP 0 IS COMPLETE — 2026-08-17
>
> All five slices shipped; a real HTTP request ran the whole pipeline end to end, **proven live over uvicorn against
> a real model**: `gemini-3.6-flash` at tier 2 after tier 1 returned 503, `STOP`, 11,507 characters, **47 of 47
> citations resolved**, in 52.7 s. **284 tests — 210 unit, 49 api, 6 integration, 19 smoke — ruff clean.**

**What Step 0 proved:** the core idea produces something useful and every layer connects. **What it did not prove:**
that it works on anything but one fixture (`quora_siamese`: one pair, one domain, one language); a second pair
belongs in Step 1. **The layer-balance rule:** the prompt layer raced ahead during slice 4 and slice 5 brought the
API up from nothing; Step 1 had to do the same for retrieval, then a hardcoded 50/50 positional split.
