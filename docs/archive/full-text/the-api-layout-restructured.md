# Full text: The API layout — restructured 2026-08-17

[Docs home](../../README.md)

## The API layout — restructured 2026-08-17

*Same session, right after slice 5 shipped. **No new product decisions** — the
comparison behaves identically. Only the shape changed, plus the error body.*

**The trigger:** one `app.py` held the app, the route, the pipeline, the upload
parsing and every failure branch. That is five reasons to change in one file,
which this file's own [layout rule](../../development/architecture-layers.md#layout--plan-the-shape-early-create-files-late)
forbids.

The shape follows the user's own two FastAPI projects — `sms-spam` and
`Lung Disease Detection` — read directly rather than invented:

| Module | Holds |
|---|---|
| `main.py` | `create_app()` and the `lifespan` |
| `config.py` | `ApiConfig`, and the project's **only** `load_dotenv` |
| `contracts.py` | `Artifact`, `Comparison` — plain dataclasses, no Pydantic |
| `schemas.py` | the wire models, including the error envelope |
| `errors.py` | one `ApiError` hierarchy, each subclass carrying `status` + `code` |
| `error_handlers.py` | `register_error_handlers()` — one envelope for every failure |
| `dependencies.py` | `LLMClientDep` |
| `uploads.py` | the HTTP edge: `UploadFile` → `Artifact` |
| `services.py` | the domain pipeline — **no FastAPI import at all** |
| `startup.py` | `validate_provider_keys()` |
| `routers/` | `compare.py`, `health.py` |
| `middleware/` | `request_id.py`, `body_limit.py` — both **pure ASGI** |

**UPDATE 2026-10-18: `services.py` no longer exists.** It was split into `ingestion.py`, `source_chunks.py`, `reading.py`, `searching.py`, `prompting.py` and `asking.py`; the map from old names to new ones is in 17.18.

**The split that carries the most weight is `services.py` having no FastAPI
types in it.** Routers speak HTTP, `uploads.py` owns the multipart edge, services
do the domain work. At Step 2, LangGraph replaces `services.py` and **nothing
else moves** — which is the test of whether a seam is in the right place.

**`contracts.py` and `schemas.py` are deliberately separate**, which neither
reference project does. Domain values change when the *pipeline* changes; wire
models change when the *API* changes. Same rule as `llm/contracts.py`.


### Five things that go past the reference projects

1. **`/api/v1` on `/compare`, while `/` and `/health` stay off it.** A probe must
   not have to know which API version is deployed.
2. **Failure responses declared on the route**, so OpenAPI documents 413, 422 and
   503 instead of only 200.
3. **The error envelope is a Pydantic model**, so its shape is documented rather
   than assembled by hand in each handler.
4. **One handler over a typed `ApiError` hierarchy**, not one handler per
   exception. A new failure is one class, not a class plus a handler plus a
   registration.
5. **The lifespan validates that at least one chain tier has an API key.** This is
   the analogue of their `validate_artifact_paths()`, and it is exactly what
   would have caught the missing `load_dotenv` **at boot** instead of at the
   first request.


### The one behaviour change

The error body moved to the house style used in both reference projects:

```
before   {"detail": "b (logo.png) is not UTF-8 text"}
after    {"error": {"code": "unreadable_upload", "message": "...",
                    "request_id": "...", "attempts": []}}
```

`code` is stable and machine-readable; `message` is for a human; `request_id`
ties the reply to the log line. `attempts` is filled only by
`generation_unavailable`.


### Two ASGI middleware, and why not `BaseHTTPMiddleware`

Both are written as raw ASGI callables, copying the reference projects' choice.
`BaseHTTPMiddleware` buffers the response and interacts badly with streaming and
background tasks; a plain ASGI class has neither problem.

- **`RequestIDMiddleware`** — a UUID per request, on `scope["state"]` and on the
  `X-Request-ID` response header.
- **`RequestBodyLimitMiddleware`** — refuses an oversized body by `Content-Length`
  *before* reading it, and falls back to counting streamed bytes when the header
  is absent or unparseable. This is the whole-body guard the per-file check could
  not provide, because the per-file check runs after parsing.

**Order matters and is easy to get backwards.** `add_middleware` prepends, so the
**last** one added is outermost. Request ID is added last on purpose: a body
rejected for size still comes back with a correlation ID.


### What the restructure did NOT add

- ~~**No `app.mount(...)`.**~~ **Added later the same day**, once there was
  something to serve — see [the page and the container](../../step0/slice-5-and-the-api.md#the-page-and-the-container--2026-08-17).
  The rule it was refused under still holds: a mount pointing at nothing is dead
  code, so `/ui` is mounted **only when the directory exists**.
- **No docstrings.** This file's own rule puts documentation in a separate pass
  with the `documentarize` skill — which is why the two reference projects read
  the way they do. The code is drafted raw on purpose.


### Mutation testing found the same bug twice in one day

Every new invariant was broken on purpose. Two tests did not bite:

1. **`test_every_error_carries_a_request_id_...` passed with the middleware
   removed**, because `error_response` falls back to a fresh UUID. It pins the
   *envelope*, not the middleware. The middleware is really pinned by
   `test_a_successful_response_also_carries_a_request_id`, where no fallback
   exists.
2. **The body-limit test had the identical self-fulfilling shape** as the upload
   test fixed hours earlier: `over = b"x" * (MAX_REQUEST_BODY_BYTES + 1)`. Raise
   the ceiling and the payload grows with it.

> **Knowing the rule does not stop you breaking it.** *A threshold test needs a
> literal on one side of the comparison* was written down the same day and
> violated again within hours. Mutation testing caught it both times; reading the
> test did not.

**Code state after the restructure: 207 unit, 34 api, 6 integration, 19 smoke,
ruff clean.** Two more passes followed the same day — the
[system-wide audit](../../step0/slice-5-and-the-api.md#the-system-wide-audit--2026-08-17) and
[the page and the container](../../step0/slice-5-and-the-api.md#the-page-and-the-container--2026-08-17) — taking it
to **210 unit, 49 api, 6 integration, 19 smoke**.
