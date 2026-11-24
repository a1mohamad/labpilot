# Section 22: Bazaarlink

[Docs home](../README.md)

### 22. BAZAARLINK — probed and added to the chain, 2026-10-18

*The user found it and asked for a smoke test, then the quota, then "add them all". Exit
AS57568 ARVANCLOUD, Frankfurt, Google 200 (checked twice; the address changed between the
checks, the verdict did not). Everything below was MEASURED the same day, except what 22.5
lists as not tested.*

#### 22.1 What it is, and which models are free

An OpenAI-compatible gateway, base `https://api.bazaarlink.ai/v1`, key `BAZAARLINK_API_KEY`.
`GET /v1/models` lists 122 models and only three have price 0:

```
qwen/qwen3.7-flash:free                    Qwen 3.7 Flash
deepseek/deepseek-v4-flash-0731free:free   DeepSeek V4 Flash, the 0731 snapshot
auto:free                                  a router over those two (the docs table)
```

The PLAIN ids `qwen/qwen3.7-flash` ($0.03 / $0.13 per million) and `deepseek/deepseek-v4-flash`
($0.20 / $0.40) are PAID, and their pages say "is a paid model". A search engine and the model
pages both said there is no free tier, and only the provider's own `/docs` page and the API
told the truth: the free ids carry a `:free` or `free` suffix.

#### 22.2 The quota: "60 a day" is 60 UNITS for the whole ACCOUNT

Read from the provider's own `/docs` page (the raw page, not a summary), then measured:

```
docs      60 requests a day per free model (x1 unpaid, x2 funded), 10 RPM, counted in
          UNITS that grow with the prompt; each model "counted separately"
header    x-ratelimit-limit 20 (the account tier: under $5 of credit = 20 RPM)
overflow  with a POSITIVE balance the extra calls are BILLED at the paid price;
          `X-Free-Fallback: false` turns that into a 429 (a downgraded call carries
          `x-bl-free-fallback: daily|rpm`)
measured  429 after only 13 calls (~70,000 prompt tokens, two of them 25K and 44K):
          "daily limit of 60 free-model requests for your account (it resets at
          00:00 UTC). Retry after 49321 seconds" - the reset time was not in the docs
```

DeepSeek was refused on its first call after only 3 small calls, so the pool looks
ACCOUNT-WIDE although the docs say per model. It is NOT proven from outside: the clean proof is
a fresh day where one model is spent and the other still answers. The units per token are
unknown and no counter exposes them (`GET /v1/key` shows requests so far, not the limit).
Other endpoints: `/credits` ($0), `/usage` (per model and key, spend 0), `/plans` (empty).

> **A quota counted in units is a token budget wearing a request budget's name.** Two big
> prompts used most of the day. I also ran Qwen's big prompts BEFORE DeepSeek's tests, and the
> pool is shared, so DeepSeek never got its turn: test the cheap cases of every model first.

#### 22.3 What was measured

| test | Qwen 3.7 Flash | DeepSeek V4 Flash 0731 |
|---|---|---|
| short code question, 3 calls | 3 of 3 whole, 2.7-3.0 s, no reasoning tokens | 3 of 3 whole, 5.6-12.2 s, ~430 hidden reasoning tokens for a 42-token answer |
| function calling, auto and forced | 2 of 2 valid, 4.1-4.3 s | NOT tested (quota) |
| JSON: `json_object`, strict `json_schema`, plain prompt | 3 of 3 valid, not fenced, 5.1-5.5 s | NOT tested |
| a needle (`CLIP_NORM=1.5; F1=0.851`) in 25,478 real prompt tokens | found, 6.8 s | NOT tested |
| the same in 43,828 real prompt tokens | found, 8.3 s | NOT tested |
| a 1,500-word report | NOT tested | NOT tested |

`chars/3` over-estimated the real tokens by 1.14-1.26x, the safe direction. Quality is one
sample on one planted bug: DeepSeek's first answer was the most exact (a slice of `k+1`
elements divided by `k`), Qwen's were shallower and one named an `IndexError`, which is wrong.

#### 22.4 What was built

```
llm/openai_compatible.py   NEW field `extra_headers`. The credentials are written LAST,
                           so an extra header can never replace them
llm/registry.py            BAZAARLINK_URL, _bazaarlink(), two tiers, tiers 51 and 52 of
                           75, right after the measured Gemma 4 31B routes
.env.example, smoke.yaml   BAZAARLINK_API_KEY (the GitHub secret was created later, the user said so on 2026-10-24)
tests                      4 new unit tests (3 for the header, 1 pinning it on every
                           tier), GATEWAYS, OUTPUT_TOO_SMALL and the reasoning excuse
                           updated, a catalogue case and a 7 s gap in the smoke tests
```

Decisions: (1) **ONE quota pool**, like Kilo and Requesty. (2) **UNSCORED, so below the
measured Gemma 4 31B** (no evidence, no promotion); Qwen first because it is fast and fully
tested. (3) **SMALL JOBS ONLY: `max_output_tokens` is 8,192**, not a report's 32,000. That is
Groq's trick, model the limit that binds, and `_check_fits` turns a report away for free
instead of letting one report spend a third of the day. The number is conservative, not
measured; both names are in `OUTPUT_TOO_SMALL` with that reason. (4) **`X-Free-Fallback:
false` on every tier**, pinned by a test: the balance is $0 so nothing can be billed today,
which is exactly why nobody would notice the header going missing. (5) No `extra_body`:
whether a reasoning field is accepted is untested, and an unlisted field is a guess.

Checked: 1057 unit and api tests pass, ruff is clean, and 8 deliberate breaks (header
dropped, header value flipped, credentials replaceable, headers never sent, one pool per
model, a full-report output cap, the secret missing from `smoke.yaml`, the key missing from
`.env.example`) each fired exactly ONE test. LIVE: the catalogue check confirms both ids are
still free, and the real smoke classified both tiers as "quota is spent" from the live 429,
which proves the URL, the headers and the error path of the shipped provider code. The SUCCESS
path through that code is NOT proven live yet, because the quota was gone.

#### 22.5 Not tested, and open

- DeepSeek 0731: function calling, JSON, big prompts. Re-run after 00:00 UTC, small prompts
  first and big ones last. Then a calibration of the units per token.
- A 1,500-word report on either model (so the 8,192 cap stays a guess).
- Whether the pool is really account-wide (see 22.2).
- Artificial Analysis scores for both. The 0731 snapshot may be the model scored as DeepSeek
  V4 Flash (34), because LiteRouter's `deepseek-v4-flash-0731:free` was renamed
  `deepseek-v4-flash:free`; that is an inference from names, not a measurement.
- **The GitHub secret `BAZAARLINK_API_KEY` had to be created by hand, and the user did
  it (said on 2026-10-24).** Without it the Monday smoke run fails on these two cases.
- Their real use is slice 11: a planner or gate chain led by a fast tier (D47). Until then
  they sit near the tail as extra insurance for small jobs.

