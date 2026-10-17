"""Structured errors that the frontend can display directly."""

from __future__ import annotations


class SherlockError(Exception):
    """An expected, user-facing error.

    ``message`` must never contain document text, detected values, or
    filesystem paths: it is sent to the client and may be logged.
    """

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
