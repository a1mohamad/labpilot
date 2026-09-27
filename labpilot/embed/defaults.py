from __future__ import annotations

DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 60.0)
MAX_BATCH_SIZE = 96
# codestral-embed is the tighter of the two: 50,000 tokens/minute, against
# mistral-embed's 20,000,000. MAX_BATCH_SIZE is derived from this number.
TIGHTEST_TOKENS_PER_MINUTE = 50_000

# GOOGLE ENFORCES ITS PUBLISHED LIMIT, so MAX_BATCH_SIZE - a Mistral number - is
# wrong for it. Measured 2026-09-24 on gemini-embedding-001, key 2:
#
#     96 texts, ~47,869 est tokens   ->  429, and the body never says "token",
#                                        so embed_batches raised instead of halving
#     40 texts, ~18,993 est tokens   ->  200
#     40 more at once, ~18,255       ->  429 - the minute's bucket, not the size
#
# Google's 429 names no metric and sends no retryDelay, so the two limits below
# are read from the account's rate-limit page and confirmed only by behaviour.
GOOGLE_TOKENS_PER_MINUTE = 30_000
# Google counts one TEXT inside batchEmbedContents as one request - finding F4,
# three 40-text calls in six seconds hit a limit of 100.
GOOGLE_TEXTS_PER_MINUTE = 100
# 40 x 510 capped tokens = 20,400, so a full batch fits the minute alone with
# room for chars/3 under-counting: the worst measured was 1.29x (Mistral,
# 59,466 real against 46,162 estimated), and 20,400 x 1.29 = 26,300 < 30,000.
GOOGLE_MAX_BATCH_SIZE = 40

# THE PACE. A batch that fits the minute is not enough - the MINUTE must fit
# too, or the second batch is refused (the third line of the table above).
# 0.9 is measured headroom, not a guess: scripts/warm_embeddings.py paced
# Google at 90% of both limits and ran 943 chunks with no minute refusal on
# 2026-09-18, which also says chars/3 does not under-count Google's tokens
# by more than that.
PACE_HEADROOM = 0.9
# 62, not 60: we stamp a request when it LEAVES and Google when it ARRIVES, so
# our window must outlast theirs. The same slack the script used.
PACE_WINDOW_SECONDS = 62.0
# Cut a paced batch so this many fit in one minute. One full 40-text batch is
# ~20,000 tokens, so ONE per minute would leave a third of the bucket unused.
PACED_BATCHES_PER_MINUTE = 2

# A 429 or 503 is a WAIT, never a SIZE - the five-way rule, applied to the
# embedder. Halving on a 429 only sends smaller batches into an empty bucket.
# 20s clears Mistral's "backend_out_of_capacity"; 60s outlasts any per-minute
# bucket. Past that, for Google, it is almost always the DAILY text budget.
RETRY_WAITS: tuple[float, ...] = (20.0, 60.0)
RETRYABLE_STATUSES = frozenset({429, 503})
