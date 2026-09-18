from __future__ import annotations

DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 600.0)
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0
# TWO retries, raised from one on 2026-09-19 for the 500 below. A 429 or a
# 503 costs 1s then 2s to retry twice, which is nothing against the 900s
# total budget that caps the whole walk.
DEFAULT_MAX_RETRIES_PER_TIER = 2
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_TOTAL_BUDGET = 900.0
RATE_LIMIT_WINDOW = 60.0
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_INTERNAL_ERROR = 500

# 500 JOINED THIS SET ON 2026-09-19, and it overturns a rule this project
# wrote down: *400 / 500 / empty / timeout -> next tier, because retrying
# cannot change it*. For Gemma that premise is simply false, and it is
# measured: gemma-4-31b answered HTTP 500 on TWO calls of three and 200 on
# the third, three times in a row, on a trivial prompt. Retrying DOES change
# it, so the old rule was throwing away the largest quota in the project -
# 57,600 Gemma calls a day - on a fault that clears by itself.
#
# The cost of being wrong is small and bounded: a genuinely broken endpoint
# now costs two extra calls and 13 seconds before the chain moves on.
RETRYABLE_STATUSES = frozenset(
    {HTTP_TOO_MANY_REQUESTS, HTTP_SERVICE_UNAVAILABLE, HTTP_INTERNAL_ERROR}
)

# A 500 carries no Retry-After and no reset time - there is nothing to read,
# so the wait is chosen rather than derived. The generic backoff is 1s then
# 2s, which is too fast for a server that is failing rather than throttling.
SERVER_ERROR_DELAYS: tuple[float, ...] = (3.0, 10.0)
SAFETY_MARGIN_RATIO = 0.10
