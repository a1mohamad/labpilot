# CI and the smoke tests

[Docs home](../README.md)

### Linting, hooks, and CI — added 2026-08-10

**One tool, one pinned version, three places.** `ruff` runs in the editor, in the
pre-commit hook, and in CI. If the versions drift, a commit that is green locally
fails in CI for no real reason — so `ruff.toml`, `requirements-dev.txt`, and
`.pre-commit-config.yaml` (`rev:`) must all name the **same** version.

- `ruff.toml` — line length 88, rules `E,F,I,UP,B` (style · unused/undefined ·
  import order · outdated syntax · common bugs).
- `.pre-commit-config.yaml` — `ruff-check --fix` and `ruff-format` on staged
  files. Needs `pre-commit install` **once per clone**: hooks live in `.git/`,
  which is never cloned or committed.
- `.vscode/settings.json` — format on save, fix and sort imports on save,
  `ruff.importStrategy: fromEnvironment` so the editor uses the venv's ruff and
  not the extension's bundled copy. Committed, because it holds project settings
  only — never a machine path.

**CI verifies; it never fixes.** Auto-fixing in CI means the pipeline pushes
commits to your branch, which needs write access and hides the problem instead of
showing it. So CI runs `ruff check .`, `ruff format --check .`, `pytest -q`.

**`CLAUDE.md` is CI-checked source, not prose — found the hard way 2026-08-28.**
`ruff format` formats Python code blocks **inside Markdown files**, so a
` ```python ` fence in this file is held to the same standard as `labpilot/`.
A block whose inline comments were aligned with six spaces instead of PEP 8's
two turned CI red:

```
--> CLAUDE.md:3956:46      1 file would be reformatted, 113 files already formatted
```

Two consequences. **Write every ` ```python ` fence here as real formatted
Python** — or tag the fence with no language when it is pseudo-code, which is
what most blocks in this file already do. And **run all three CI commands before
saying a change is clean**; `pytest -q` alone passed happily while
`ruff format --check .` was failing.

**CI brings its own database — 2026-09-04.** A `pgvector/pgvector:pg17`
service container, `DATABASE_URL` set at job level, and one step that installs
the extension into `public` so the shape matches Supabase. **No secret**, so
pull requests from forks work. Do **not** point CI at the real project: every
push would share one database, and two concurrent jobs both running
`drop schema labpilot_test cascade` is the 2026-09-04 flake with a new cause.

> **The tests that most need CI are the ones that skip when it is not
> configured.** A `database` test is green-by-absence, so "CI passes" said
> nothing about ten of them for a week.

**Two workflows, and the split is about quota:**

| Workflow | Trigger | Runs | Cost |
|---|---|---|---|
| `ci.yaml` | every push and PR | lint + unit + **database** tests | **zero** — no provider is called |
| `smoke.yml` | manual button + Mondays 06:00 UTC | smoke only | ~1 request/week |

The weekly smoke run exists for one reason: **free models disappear without
warning**. Better to get an email on Monday than to find out mid-session. Secrets
come from GitHub Actions secrets, never from the YAML — which is why the provider
reads its key at call time rather than storing it.

*Updated 2026-08-11:* the smoke run now costs **4 requests a week** — 2 on
OpenRouter (tiers 1 and 4), 2 on Google (tiers 2 and 3). Both
`OPENROUTER_API_KEY` and `GOOGLE_API_KEY` must exist as repository secrets.

**A bug worth remembering:** the workflow originally set the env var as
`OPENROUTE_API_KEY` — missing the `R` — while mapping it from the correctly
named secret. The secret reference was right; the *variable name* was wrong, so
every scheduled run failed with `OPENROUTER_API_KEY is not set`. A typo on the
left of the colon is invisible to YAML validation and to CI, because the only
thing that notices is the code reading `os.environ`.

#### The smoke suite parametrizes over `CHAIN` — added 2026-08-17

Four per-provider smoke files (`test_google/mistral/openrouter/cloudflare.py`)
were replaced by **one file that parametrizes over `CHAIN` itself**. Add a tier,
and it gets smoke coverage automatically. Before this, five of fifteen models had
no smoke test at all and nobody noticed.

Three details that make it work:

- **A known-dead tier is `xfail(strict=False)`, not deleted.** GLM-5.2 reports
  `XFAIL` quietly every week — and the day Mistral restores it, the result flips
  to **`XPASS`**, which is exactly the signal we want and would otherwise never
  arrive.
- **The output budget is per provider**, `min(8192, max_output, context // 2)`.
  A fixed 8,192 asked Groq for more than its entire 8,000 budget.
- **8,192 is the reasoning floor.** At 2,048 `mistral-medium-latest` sometimes
  spends the whole budget thinking and returns nothing — flaky, not broken.

#### PARAMETRIZE OVER THE LIST THE CODE USES, NEVER OVER ITS PARTS — 2026-09-19

*The third time this project has shipped a tier nobody was watching, and the
first time the cause was named properly.*

The rerank smoke run parametrized over **the two halves** of chain 3:

```
RERANK_CHAIN       the cross-encoders        3 tiers
LLM_RERANK_ORDER   the Gemini tiers          4 models x 2 keys
```

Both lists are real, both are complete, and **neither is what the ask path
calls**. `api/reranking.CHAIN` is — it is assembled from those two *plus*
anything placed between them. So when Jev was shipped at **position 3**, it
was covered by nothing, while every tier on either side of it had weekly
liveness. A gap of exactly one tier, and the newest one.

**The fix is to iterate the assembled chain**, which cannot miss a tier by
construction:

```
before   @parametrize("reranker", RERANK_CHAIN)      3 cases
         @parametrize("reranker", LLM_TIERS)         8 cases
after    @parametrize("reranker", CHAIN)            12 cases, Jev included
```

> **A test that iterates the INPUTS to a structure does not test the
> structure.** Parametrize over the object the production code actually
> reaches for. Two lists that are each complete can still leave a hole
> between them, and the hole is invisible — every case passes.

**Three occurrences now, same shape each time:** five of fifteen generator
models had no smoke test at all (2026-08-17); the four LLM tiers that *led*
chain 3 had no liveness check (slice 6); and Jev (2026-09-19). Each was found
by asking "which tier is not in this list?" rather than by anything failing.

#### A FIELD TEST IS NOT THE RULE — the same review pass, 2026-09-19

`test_only_known_tiers_cannot_serve_a_full_report` compares one field:

```
max_output_tokens < REPORT_MAX_TOKENS
```

The chain applies a different rule. `_check_fits` enforces the **sum against
the context window**, so a tier with a generous `max_output` and a small
CONTEXT passes the field test and still cannot serve a report:

$$
26{,}000\ \text{prompt} \;+\; 32{,}000\ \text{output} \;=\; 58{,}000
$$

GLM-5.2's move to OpenRouter brought exactly that shape — a 32,768 context —
and was caught by its output cap instead, **by luck**. The next one would sit
in the report chain and fail at the provider on every report.

`test_every_tier_we_believe_can_serve_a_report_really_can` calls `_check_fits`
with a report-sized prompt instead. Proven by the mutation that the field
test cannot see: raise `max_output` to 32,768 and drop the name from the
list — the old test stays green and the new one fires **alone**.

> **When a test checks a FIELD and the code applies a RULE, the test is a
> proxy.** Proxies drift. Call the rule.

#### A unit test now guards the workflow file

`test_every_chain_env_var_is_mapped_in_the_smoke_workflow` reads
`.github/workflows/smoke.yaml` and asserts the exact string
`NAME: ${{ secrets.NAME }}` for every `api_key_env` in `CHAIN`.

**This is the test that would have caught the 2026-08-11 `OPENROUTE_API_KEY`
typo** — a wrong variable name on the left of the colon, invisible to YAML
validation and to CI, which silently broke every scheduled run. It was verified
to fail on a misspelling before being trusted.

> **If CI configuration can drift from code, a unit test should check it.** The
> workflow is just a text file; reading it costs nothing and runs on every push.

**Secrets are still manual.** Adding a provider needs the GitHub repository
secret created by hand — the test catches the *mapping*, never the secret's
existence. `GROQ_API_KEY` was added to the workflow on 2026-08-17 and **the
repository secret must be created**, or Monday's run fails on tier 12.

**Scheduled workflows run from the default branch only.** A fix living on a
feature branch does not affect Monday's run until it reaches `main`.

**CD is deferred to Step 3.** There is nothing to deploy until Docker exists.
