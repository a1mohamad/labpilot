# The cleanup before slice 12 (2026-11-24)

[Docs home](../README.md)

Dead code out, repeated code in one place, the long functions split, and the old limit of 48 claims removed. The
user asked for all of it, and Claude typed it (a one-task permission).

## The decisions

| # | decision |
|---|---|
| **D140** | **`join_claims` keeps the whole list.** The limit of 48 method claims (`MAX_CLAIMS`) is gone: it was left from slice 7, and D85 already said that the list is kept whole. `CLAIMS_VERSION` is 5, so the stored claims are made again. The limit for a really big A is chosen in slice 12 |
| **D141** | **Every tool call goes through `ask_tool`** (claims, gate and planner too). A wrong answer is checked by the same function that reads it, so the chain asks the next model. A plan that does not fit the files is refused even when the chain let it through |
| **D142** | **Code that nothing calls is deleted, not kept**: `retrieval/usage.py`, `rerank/cloudflare.py`, `keyword_search`, `weighted_rrf`, the templates FULL, CORE, REPORT, SCAN and COMPARE, `REPORT_MAX_TOKENS`, `GEMINI_3_5_FLASH`, `GEMINI_3_7_FLASH`, `KINDS`. Their history is in git and in the older pages |

## Where each piece is now

| piece | file |
|---|---|
| the shape of a list tool, `number`, `index`, `is_located` | `agent/_schema.py` |
| "a finder that fails gives nothing" | `agent/_safety_net.py` (`or_nothing`) |
| which node runs next | `agent/choices.py`; `agent/graph.py` only draws the edges |
| the measure and stuff nodes | `agent/measure.py` |
| the call that writes the answer, and its error | `api/answering.py` |
| `search_one`, `whole_side`, `or_no_summary` | `api/searching.py`, `api/reading.py`, `api/summaries.py` |
| the request id header | `api/headers.py` |
| `SIDES`, `LINE_CHARS` | `ingest/contracts.py`, `agent/final_merge.py` |
| the shape Cohere and Voyage share | `rerank/documents.py` |
| the other Google accounts | `_account(provider, n)` in `llm/registry/google.py` |

The nodes stay functions (a class for each node was discussed and not chosen). `build_answer_prompt` is now a whole
prompt, or a fitted prompt.

## The live test of the claims (M35)

| # | what was measured |
|---|---|
| **M35** | The real `make_claims_extractor` (real route, real groups) on three references, with the list cut at 48 and whole, from the SAME answers. 11 runs. Key: the hand-made facts of quora (12 mismatch, 20 match), and 12 (adam) and 15 (otp) facts written for this test after reading A |

| reference | runs | method claims | lost by the old limit | facts found, whole list | facts found, cut at 48 | seconds |
|---|---|---|---|---|---|---|
| quora (18 parts, 2 groups) | 4 | 43 to 60 | 0 to 12 | 11, 11, 11, 10 of 12 mismatch; 20, 20, 20, 18 of 20 match | 10, 10, 10, 10; 18, 18, 18, 18 | 8 to 12 |
| adam (39 parts, 8 groups) | 4 | 56 to 78 | 8 to 30 | 8, 9, 12, 11 of 12 | the same | 13 to 29 |
| otp (44 parts, 11 groups) | 3 | 102 to 132 | 54 to 84 | 15, 15, 15 of 15 | 13, 12, 10 | 15 to 58 |

**Accepted.** The whole list never found less, and on otp the old limit lost real facts (the minimum of 128 bits for the
secret, the floor of the time step). Every group answered, no run failed, and no group was missing.

What is still weak, and not new:

- **Small facts are repeated between groups** ("beta1 is 0.9" twice). 1 to 15 near repeats in a run; on otp they are test
  vectors, which differ by one value and are `result` claims, so nothing audits them.
- **The update rule of Adam was missing in the first run** (PDF formulas). The adam key is a loose regex screen, and it
  was written after A was read, so its numbers are a rough sign only.
- **Two facts of quora (G31 always, G26 and G30 sometimes) are not listed.** That is the wording, the same as before.
- **The cost moves to the audit:** 30 facts for each call and 2 votes for each group of B. Otp goes from 2 to 4 or 5
  batches, so about twice the calls. Slice 12 chooses the limit, with M12 and M13.
- Flash-Lite 3.5 key 1 and 2 were nearly spent: Flash-Lite 3.1, Gemma and Nemotron gave some of the groups.

## Tests

New: `test_schema_helpers.py`, `test_choices.py`, `test_answering.py`, and `whole_side`, plan and claims cases.
Deleted with their code: the tests of `usage`, the Cloudflare reranker, rank fusion, `keyword_search`, the old templates and
the old baseline smoke test.

**Checked:** unit and api 2,677 passed, 5 skipped; 60 related database tests passed; 22 deliberate breaks, 20 caught
and 2 survived (the order of the evidence, the raw header name). `tests/api/test_evidence_first.py` was written for both, and it
caught both when they were repeated, and one more break of the ids. In one run of the whole database folder at the same time as
live calls, two tests of `test_ask.py` failed; they passed alone afterwards, and the reason was not read.
