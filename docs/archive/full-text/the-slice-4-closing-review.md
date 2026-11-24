# Full text: The slice 4 closing review — 2026-09-05

[Docs home](../../README.md)

## The slice 4 closing review — 2026-09-05

*Run across the whole system, not across the new code, asking only the standing
question: **which real failure is still unprotected?** Two gaps found, two tests
added, **one candidate rejected because a linter already covers it**, and one
predictable future bug recorded instead of fixed.*
**559 passed, 28 skipped, 1 xfailed. Both new invariants mutation-tested.**


### Gap 1 — the entire API-quota gate rested on a decorator

`tests/conftest.py` skips by **marker alone**:

```python
if "smoke" in item.keywords:
    item.add_marker(skip_smoke)
```

So a smoke test written without `@pytest.mark.smoke` runs **on every push** and
spends real provider quota. Nothing checked it, and nothing would report it —
the suite would simply be slower and the quota would be gone.

`test_every_smoke_test_carries_the_smoke_marker` parses each file in
`tests/smoke/` and fails the build if any test function is unmarked. It reads
module-level `pytestmark` as well as decorators, so either style passes.

> **A cost gate that depends on remembering is not a gate.** The rule was
> written in this file and enforced by nothing.


### Gap 2 — nothing stopped a default-run test from loading real credentials

`load_dotenv` is the first step of reaching a real service. Measured across the
whole suite, it appears **only** in `tests/integration/conftest.py` and
`tests/smoke/` — exactly the cost split this file describes. Nothing held it
there.

`test_no_default_test_loads_real_credentials` fails if a file under
`tests/unit/` or `tests/api/` loads `.env`. Both folders run on every push.

**It pins a property the suite already has**, rather than asking for a change —
which is the cheapest kind of invariant to add and the easiest to lose.


### Rejected — and the reason is worth more than the test would have been

A third test was written and **deleted**: *"every name in each package's
`__all__` is importable"*, modelled on the existing
`test_every_public_name_is_importable` in `unit/llm/`.

~~**Ruff already catches it.**~~ **FALSE, and it cost a live defect — measured
2026-09-13.** `F822` is in the `F` rule set, and `ruff.toml` has had it enabled
since day one. But **ruff EXEMPTS `__init__.py` from F822**, because a re-export
door legitimately names things it did not define. Same ruff, same rule, two
files of identical content:

```
a plain module   ->  F822 Undefined name `ghost` in `__all__`
an __init__.py   ->  All checks passed
```

**So the deleted test was the only thing holding that rule, and the bug arrived
in the newest package.** `labpilot/rerank/__init__.py` listed
`RERANK_MAX_TOKENS` in `__all__` and never imported it, so
`from labpilot.rerank import *` raised `AttributeError` while the full suite and
**both** ruff commands stayed green. Fixed 2026-09-13, and the test is now
`tests/unit/test_public_api.py`, over **every** package.

> **The rule below is right. The ANSWER to it was wrong, and only running the
> linter against the real case could tell the two apart.**

> **Before adding a test, ask what already fails when the rule is broken** —
> then **prove** it fails, on a file of the kind you actually have. A linter
> rule is not a linter rule *everywhere*; exemptions are invisible until you
> write the broken case and watch nothing happen.

*Only packages are checked. `tokens.py` and `_text.py` are plain modules, where
F822 genuinely does fire — so guarding those too would be the duplicate the
rule warns about.*

*`test_every_public_name_is_importable` in `unit/llm/` was DELETED with it.
Mutating `llm/__all__` fires **both** tests, so the `llm`-scoped one can never
fire alone — the same criterion that deleted
`test_nothing_imports_the_entry_layer`. This file previously said deleting it
"would be churn for nothing"; once a general test exists, keeping it is the
churn.*


### Recorded, not fixed — the boundary slice 7 will break

`api/services.py` catches `LoaderError`, `NotUtf8Text`, `LooksGenerated`,
`OSError` and `AllFreeTiersExhausted`. It knows **nothing** about `StoreError`
or `EmbeddingError`.

So the moment slice 7 wires the store, every one of `UnknownArtifact`,
`ModelMismatch`, `ConnectionFailed`, `NotConfigured` and `EmbeddingError` lands
in the **500 handler** — reported as *our* bug rather than as the user's input
or a provider outage.

**This is the third time this exact shape is predictable.** Slice 3 hit it twice
in one day: a malformed notebook reached the 500 handler, and then the same
error inside `chunk_source` silently truncated an entire repository walk.

> **When you add an error type, walk every boundary that already catches
> errors.** No handler is written today because nothing calls the store yet —
> a handler with no caller is dead code. But slice 7 must not discover this by
> watching a 500.

**Slice 7's checklist, then:** map `NotConfigured` and `ConnectionFailed` to a
**503** (our infrastructure is down, like `AllFreeTiersExhausted`), and
`UnknownArtifact` and `ModelMismatch` to a **422** or a 500 depending on whether
the caller could have avoided it. Decide it there, with the caller in front of
you.
