from __future__ import annotations


class LoaderError(Exception):
    pass


class NotUtf8Text(LoaderError):
    pass
