# Full text: The system-wide audit — 2026-08-17

[Docs home](../../README.md)

## The system-wide audit — 2026-08-17

*Asked of the whole project once slice 5 closed: **which real failure is still
unprotected?** Not "where is coverage thin". Four gaps, and **two were already
broken**.*


### `pydantic` and `starlette` were imported but never pinned

```
imported by labpilot/ : dotenv, fastapi, pydantic, requests, starlette
requirements.txt      : fastapi, python-dotenv, python-multipart, requests, uvicorn
```

Both arrived transitively through FastAPI, so a FastAPI upgrade could have moved
either version underneath us with nothing failing — and `starlette` is what both
ASGI middleware are built on. This file already says `requirements.txt` holds
**direct** dependencies; a direct import is a direct dependency.

**CI cannot catch this by construction**: it installs `requirements-dev.txt`,
which pulls the whole tree in regardless. Only a test that reads the imports can.


### The API's own knobs were documented nowhere

`MAX_UPLOAD_BYTES`, `MAX_REQUEST_BODY_BYTES`, `CORS_ALLOW_ORIGINS` (and later
`FRONTEND_DIR`) are read from the environment by `ApiConfig` and appeared in no
template. **A knob nobody knows about is a knob nobody can turn.** Same failure
as `.env.example` claiming "~1,500 requests/day".


### A test of mine that lied

`test_the_documented_failures_are_the_ones_the_endpoint_can_raise` asserted

```python
assert {"200", "413", "422", "503"} <= set(responses)
```

A hardcoded set, compared with `<=`. Adding an `ApiError` with a new status would
leave it green while OpenAPI misdescribed the endpoint. **Its name promised what
it did not do.** It now derives the statuses from the `ApiError` hierarchy.


### What went in

| Test | Catches |
|---|---|
| `test_every_package_labpilot_imports_is_pinned` | a direct import missing from `requirements.txt` |
| `test_every_requirement_is_pinned_to_an_exact_version` | a `>=` creeping in |
| `test_every_environment_variable_the_code_reads_is_documented` | an undocumented knob |
| `test_every_status_the_endpoint_can_raise_is_documented` | OpenAPI drifting from the error hierarchy |
| `test_no_two_errors_share_a_code` | copy-paste making two failures indistinguishable |
| `test_the_body_limit_middleware_speaks_the_same_envelope` | the hand-built JSON drifting from `ErrorEnvelope` |
| `test_an_unexpected_exception_becomes_a_500_...` | the 500 handler, and that internals never leak |

`tests/unit/test_packaging.py` reads `requirements.txt` and `.env.example` by
AST-scanning `labpilot/`. It sits at the top of `unit/` because it crosses every
package.

**The 500 test needed a second client.** `TestClient` **re-raises server
exceptions by default**, so the handler never runs and cannot be observed. Only
`raise_server_exceptions=False` sees what a browser would.


### Mutation testing caught a third loose assertion

Five of six bit. The env-var one did not: it searched the whole file text, so a
name still mentioned in a **neighbour's comment** counted as documented. It now
matches a declaration line.

> That is three in one day, all the same shape: **an assertion whose input can
> satisfy it by accident.** Reading the tests caught none of them; mutating the
> source caught all three. **Mutation testing is not optional here — it is the
> only thing that has ever found these.**
