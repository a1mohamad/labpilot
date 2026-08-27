from __future__ import annotations


class SourceError(Exception):
    pass


class SourceTooLarge(SourceError):
    pass


class SourceNotFound(SourceError):
    pass
