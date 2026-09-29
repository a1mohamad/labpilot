from __future__ import annotations


class RerankError(Exception):
    # `status` lets a caller branch on WHAT failed without reading the message -
    # the rule LLMError and EmbeddingError already follow. None means the failure
    # never reached an HTTP status (no key, a timeout, a bad shape).
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
