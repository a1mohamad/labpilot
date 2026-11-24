from __future__ import annotations

DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 600.0)
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOTAL_BUDGET = 900.0
RATE_LIMIT_WINDOW = 60.0
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_INTERNAL_ERROR = 500

# THE RETRY RULE (D129, decided 2026-11-23 on 497 streamed calls). A tier whose
# call fails FAST is asked again once, after 1 second, and then the walk goes to
# the NEXT tier. A 503 ("high demand") is not asked again: on an evening when
# Google was overloaded the same key answered 22% of the first tries and 24% of
# the retries, so a retry only spent time that the next key or model could use.
RETRY_DELAYS: tuple[float, ...] = (1.0,)
# A failure later than this came from a slow or stuck tier, and is not retried.
FAST_FAILURE_SECONDS = 10.0
# A provider that asks for a longer wait than this is left for the next tier.
RETRY_WAIT_MAX = 3.0

# A tier is retried for the failures a second try can cure: no answer at all (a
# reset connection, a stream that broke), and a failing gateway (500, 502,
# 504). It is NOT retried for a 429 or a 503 (the tier rests, _health.py), or for
# a refusal that cannot change: 400, 401, 403, 404, 413, 422, "not on this plan", a
# call that was refused locally, or a hang that was cut off (DEFAULT_CALL_STOP).
RETRYABLE_STATUSES = frozenset({408, 425, 500, 502, 504})

# A call that has not answered after this many seconds is given up and the walk
# goes on. It is NOT a timeout in the old sense: normal calls take 2 to 10
# seconds, a report 150 to 400, and this only fires on a HANG. One Token Harbor
# call stayed open for more than 40 minutes (2026-11-16) because the server kept
# the connection alive, so a read timeout, which counts the time between bytes,
# never fired. A route may set its own number later (lesson 2); None turns it off.
DEFAULT_CALL_STOP: float | None = 300.0
SAFETY_MARGIN_RATIO = 0.10

# A ROOM is the per-minute allowance of one quota pool (D70): how many input
# tokens and how many requests it takes in any 60 seconds. Google counts a room
# for each (key, model); Token Harbor counts one for the whole account.
ROOM_WINDOW_SECONDS = 60.0
# Book only this share of a published limit, because our token count is an
# estimate (the same 10% the length check uses) and a refused call still counts.
ROOM_HEADROOM = 0.9
# A tier whose account must rest between two calls (LiteRouter, 8 seconds) is
# used when the rest is this short or none; otherwise the walk skips it at once
# and does not wait. A first guess, to be tuned on the routing measurements.
TURN_WAIT_MAX = 2.0

# How many tiers may give an answer that the CALLER rejects (a plan that is
# readable and still wrong) before the walk stops. A rejected answer costs a
# real request, so without a limit one mistaken rule in the caller would walk
# the whole chain on every call. 3 is a first guess, to be measured.
DEFAULT_MAX_REJECTED_ANSWERS = 3

# At most this many calls of one `generate` are open at the same time: the first,
# and a helper for each time it is late again (LLMClient.hedge_after).
MAX_OPEN = 3
# A late call that found no free helper looks again after this many seconds.
LOOK_AGAIN = 3.0
# A resting tier is asked after all, when nothing else is left, if its rest ends
# within this many seconds. A longer rest is a spent quota.
LAST_RESORT_REST = 120.0
