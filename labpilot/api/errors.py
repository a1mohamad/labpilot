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


class SecretUpload(ApiError):
    status = 422
    code = "secret_upload"


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


class EmbeddingUnavailable(ApiError):
    status = 503
    code = "embedding_unavailable"


class StorageUnavailable(ApiError):
    # 503, never 404. The database being unreachable is OUR infrastructure
    # failing, the same class as AllFreeTiersExhausted - the user's file was
    # fine. A 404 would tell them their upload was not found, which is a lie
    # about whose fault it is.
    status = 503
    code = "storage_unavailable"


class UnknownArtifactId(ApiError):
    # 404, not 503. StorageUnavailable is 503 because the database being down
    # is OUR failure; an id we never stored is a fact about the REQUEST, and
    # the caller could have avoided it.
    status = 404
    code = "unknown_artifact"


class ArtifactSidesClash(ApiError):
    # A comparison needs one reference and one subject. The side is baked into
    # the artifact id by _artifact_id - `f"{side}-{hash}"` - so two ids from
    # the same slot is not a comparison at all, and the prompt would have no
    # side B to walk.
    status = 422
    code = "artifact_sides_clash"


class ArtifactChanged(ApiError):
    # 409, and it is nobody's bug. measure() and search() are two round trips,
    # and write_artifact DELETES then re-inserts - so re-ingesting an artifact
    # with a different embedder moves the model under a request already in
    # flight. A 500 would blame us; a 404 would blame the user. Retrying fixes
    # it, so the status has to say that.
    status = 409
    code = "artifact_changed"


class SourceTooLargeToIngest(ApiError):
    # 413, the same class as an oversized upload: the repository really is too
    # big for us. Refuse rather than truncate - half a corpus searched silently
    # returns confident wrong answers, which is worse than a rejection.
    status = 413
    code = "source_too_large"


class UnsafeArchiveUpload(ApiError):
    # 422. CPython's zipfile already strips `..` and drive letters, measured -
    # so the danger is not escape, it is the SILENT REWRITE that follows. A
    # zip bomb is the other half: 48KB declaring 50MB.
    status = 422
    code = "unsafe_archive"


class UnreadableSource(ApiError):
    # 422 for every remaining way a source will not open: a URL we refuse, a
    # clone that failed, a path that is not there. All are facts about the
    # REQUEST, and all are things the caller can fix.
    status = 422
    code = "unreadable_source"
