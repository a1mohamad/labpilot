from __future__ import annotations

import email.utils
import time

from labpilot.llm._http import (
    error_from_response,
    reset_at_epoch,
    retry_after_seconds,
)


class FakeResponse:
    def __init__(self, status_code, headers):
        self.status_code = status_code
        self.headers = headers
        self.text = "rate limit exceeded"


def test_error_from_response_carries_the_rate_limit_headers():
    error = error_from_response(FakeResponse(429, {"Retry-After": "5"}), "Tier 1")

    assert error.status == 429
    assert error.retry_after == 5.0
    assert "HTTP 429" in str(error)


def test_retry_after_reads_plain_seconds():
    assert retry_after_seconds({"Retry-After": "12"}) == 12.0


def test_retry_after_reads_an_http_date():
    header = email.utils.formatdate(time.time() + 30, usegmt=True)
    assert 25 <= retry_after_seconds({"Retry-After": header}) <= 31


def test_retry_after_is_none_when_the_header_is_absent():
    assert retry_after_seconds({}) is None


def test_reset_at_converts_milliseconds_to_seconds():
    assert reset_at_epoch({"X-RateLimit-Reset": "1800000000000"}) == 1_800_000_000.0


def test_reset_at_treats_a_small_number_as_a_duration():
    reset = reset_at_epoch({"X-RateLimit-Reset": "20"})
    assert 18 <= reset - time.time() <= 22
