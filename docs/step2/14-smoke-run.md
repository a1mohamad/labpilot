# Section 14: the weekly smoke run

[Docs home](../README.md)

### 14. THE WEEKLY SMOKE RUN WAS RED FOR A MONTH — 2026-09-29

*Found by reading the run history instead of the code, when the user asked
whether CI had other problems. **Committed by the user on 2026-09-29 (14 small
commits, pushed) and NOT YET RUN ON GITHUB** - only a real Monday run (or
`gh workflow run smoke.yaml`, about 80 requests) can prove them.*

**Four Mondays in a row failed.** 2026-09-07: 4 failed. 09-14: 8. 09-21: 26.
09-28: **41 failed, 36 passed**. An alarm that is always red tells you nothing,
and the run could not separate a dead provider from a wrong setting.

#### 14.1 What the 41 failures of 2026-09-28 really were

| cause | failures | verdict |
|---|---|---|
| a secret missing or never passed to the run: Kilo 9, Requesty 3, **Voyage 4** | 16 | **configuration** |
| Google key 2 answering `403 PERMISSION_DENIED - "Your project has been denied access"` | about 12 | the account-restriction signature of 2026-08-11. The GitHub secret held a key that Google refuses. **Replaced by the user 2026-09-29, unverified** |
| Google key 1 answering `503 UNAVAILABLE - "This model is currently experiencing high demand. Spikes in demand are usually temporary."`, one Gemma `500`, one connection reset | about 9 | **Google's own capacity, not a key problem.** The same sentence appears in the 09-21 run. The chain retries a 503; the smoke test did not |
| Mistral answering `429 "Rate limit exceeded"` on Medium, Magistral and Devstral | 3 | ~~a spent MONTHLY quota~~ **WRONG, corrected 2026-10-05: the allowance is back ($0 of $10) and the models still answer 429 with a limit of 0 - see [section 16](16-mistral.md#16-mistrals-chat-models-are-at-zero-and-the-call-was-not-the-problem--2026-10-05).** It appeared in all four runs |
| DeepSeek V4 Flash on OpenRouter answering `404` | 1 | a dead route. It was in the REGISTRY's `KNOWN_DEAD` and not in the smoke test's own copy |

**Google key 1 and key 2 are two different failures, and they were read as
one.** Key 1 is Google being busy and clears by itself. Key 2 was a wrong
credential and never would. The status code said which (`503` against `403`);
the count of "Google failures" did not.

#### 14.2 THE VOYAGE HOLE - a third case of the same mistake

`VOYAGE_API_KEY` existed as a GitHub secret since 2026-08-11 and **`smoke.yaml`
never had a line passing it into the job**. `git log -S` shows it was never
there. A secret is only STORED on GitHub; it reaches the test process only when
the workflow maps it. Four Voyage tests failed "is not set" every week, so
Voyage has never had a weekly liveness check.

Two older tests looked like they covered this and did not: one walks the
generator `CHAIN`, one walks the embedder `MIGRATION`, and the rerankers are
neither. Cohere only escaped because it is also an embedder.

`test_every_env_var_the_shipped_rerank_chain_reads_is_mapped_in_the_smoke_workflow`
walks the ASSEMBLED chain the ask path calls. It is bound at import, because
`tests/conftest.py` empties `labpilot.api.reranking.CHAIN` for every other test.
Mutation results: removing the Voyage line and removing `JEV_PROXY_URL` each fire
it ALONE (nothing checked Jev's secret before); removing Cohere's fires it and
the embedder test, as expected.

#### 14.3 WHAT WAS CHANGED

```
tests/smoke/live.py       NEW. call_live() decides, in one place, what a live
                          failure means. tier_case() marks dead routes FROM THE
                          REGISTRY
                            transient   503 / 500 / 502 / a network fault
                                        -> wait 10s then 20s and retry, the way
                                        the chain does
                            spent quota a 429 the chain's own pool_is_exhausted()
                                        recognises, or one that persists after
                                        every retry -> XFAIL with the provider's
                                        own words. Not red: the tier is fine
                            the rest    403 / 404 / 400 / a missing key -> a real
                                        failure AT ONCE. Retrying a missing key
                                        would cost 30s and hide it
test_every_tier / test_rerankers / test_embedders   go through it
smoke.yaml                VOYAGE_API_KEY mapped; pytest now runs with -rxX so an
                          xfail's reason is printed, not just counted
rerank/errors.py          RerankError gained `status`, the rule LLMError and
                          EmbeddingError already follow. base.py sets it on a
                          non-200; LLMReranker copies it from the error it wraps
```

**`RerankError.status` is a product change made for a test's sake, and it is the
right one.** The alternative was parsing `"HTTP 503"` out of the message, which
is exactly what this file says a caller must never do. A wrapped error keeps its
status, so a spent Gemini pool behind a reranker is still recognised as spent.

**TWO LISTS OF DEAD TIERS, and it is the same disease as the missing Voyage
line.** The smoke test kept `KNOWN_DEAD = {"GLM-5.2"}` while the registry named
four routes, so three dead routes failed every Monday. `test_gateway_tiers_are_free`
already imported the registry's list; `test_every_tier` had not. Both smoke tests
and the registry now share one list, and a text test fails if a private copy
returns.

> **A test that keeps its own copy of a list drifts from the code that owns it.**
> Three cases now: the two halves of the rerank chain (Jev, 2026-09-19), the
> rerank env vars (Voyage, today) and the dead-tier list. Iterate the object the
> code uses, or import the list it defines.

**28 tests were added on top of the Voyage mapping test** (unit and api went
840 to 868, counted 2026-09-29) - the helper, the status field, the wiring - and
every rule was broken on purpose. 13 mutations, each fired on the test meant to
catch it. **One was first a fake:** a bare `ValueError` behaves the same under a narrow
`except` and a broad one, so the test could not fail; the fault now carries a
network cause and does. Two more tests read the smoke files as TEXT to prove they
go through the helper, because importing them runs `load_dotenv`, which unit
tests must not do.

#### 14.4 OPEN, and none of it is fixed

- **Nothing here has run on GitHub.** The run that proves it is the next Monday.
- ~~**Mistral's monthly cap and the embedder primary.**~~ **ANSWERED 2026-10-05
  ([section 16](16-mistral.md#16-mistrals-chat-models-are-at-zero-and-the-call-was-not-the-problem--2026-10-05)):**
  it is per MODEL, not a monthly cap. Both embedders answer 200 at 60 requests a
  minute on the same key, so the ingest order in `MIGRATION` is safe.
- **A tier the account cannot use still costs a call on every report that
  reaches it.** The monthly-quota reading this bullet was written under was
  wrong (section 16), but the cost is real: the chain forgets a dead pool between
  requests. The three Mistral chat tiers now sit at the END of the chain, so only
  a report that has already failed everywhere else pays for them. A cross-request
  memory of a dead pool would fix it for good; it is state, so it was not built
  unasked.
- **A different failure, seen only in the 09-21 log:** `test_ask_answers` failed
  with tiers 1-9 spending the whole 900s budget and **31 tiers skipped as "time
  budget spent"** - one of them a Cloudflare 408. That is the Step 2 latency
  problem showing up in CI, and it is slice 1's evidence.
- **The Gemma reranker still declines about 1 query in 17**, and
  `declined == 0` is asserted. It will fail a Monday by chance. Not retried,
  because a decline is a model answer, not a network fault.
