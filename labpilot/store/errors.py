from __future__ import annotations


class StoreError(Exception):
    pass


class NotConfigured(StoreError):
    pass


class ModelMismatch(StoreError):
    pass


class ConnectionFailed(StoreError):
    pass
