from __future__ import annotations

DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 600.0)
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOTAL_BUDGET = 900.0
RATE_LIMIT_WINDOW = 60.0
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_INTERNAL_ERROR = 500

# THE RETRY RULE (decided 2026-11-16, after the slice 11 measurement). A tier is
# called; if it does not answer, it is asked again after 1 second, and once more
# after 3 seconds, and then the walk goes to the NEXT tier at once. The old rule
# (one or two retries, a backoff that grew from 1 s, a 3 s and 10 s wait for a 500,
# a wait for whatever Retry-After said, and a 600 s read timeout) spent minutes
# on one dead tier while tiers on other providers were free to answer.
RETRY_DELAYS: tuple[float, ...] = (1.0, 3.0)

# A tier is retried for the failures a second try can cure: no answer at all (a
# reset connection, an empty reply), a busy server (429 for a minute, 502, 503,
# 504) and a failing server (500). It is NOT retried for a refusal that cannot
# change: 400, 401, 403, 404, 413, 422, a daily 429, "not on this plan", a call
# that was refused locally, or a hang that was cut off (see DEFAULT_CALL_STOP).
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

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
