from __future__ import annotations

from labpilot.llm import Attempt


class ApiError(Exception):
    status: int = 400
    code: str = "api_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidQuestion(ApiError):
    status = 422
    code = "invalid_question"


class UnreadableUpload(ApiError):
    status = 422
    code = "unreadable_upload"


class UnnamedUpload(ApiError):
    status = 422
    code = "unnamed_upload"


class EmptyArtifact(ApiError):
    status = 422
    code = "empty_artifact"


class UploadTooLarge(ApiError):
    status = 413
    code = "upload_too_large"


class ArtifactsTooLargeToCompare(ApiError):
    status = 413
    code = "artifacts_too_large_to_compare"


class GenerationUnavailable(ApiError):
    status = 503
    code = "generation_unavailable"

    def __init__(self, message: str, *, attempts: tuple[Attempt, ...]) -> None:
        super().__init__(message)
        self.attempts = attempts
