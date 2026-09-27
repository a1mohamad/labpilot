from __future__ import annotations


class EmbeddingError(Exception):
    # `status` and `retry_after` let a caller branch on WHAT failed without
    # reading the message - the LLMError rule, one layer over. None means the
    # failure never reached an HTTP status (no key, a timeout, a bad shape).
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
