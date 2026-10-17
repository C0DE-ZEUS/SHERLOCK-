"""Basic abuse protection for public deployments.

A per-IP sliding-window rate limit on the expensive endpoints, plus a cap on
how many scans/redactions run at the same time so one visitor cannot exhaust
the server's CPU or memory. Both are in memory, matching the rest of the app.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Iterator

from app.config import settings
from app.errors import SherlockError


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        if self.limit <= 0:  # disabled
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise SherlockError(
                    "rate_limited",
                    "Too many files in a short time. Please wait a few minutes and try again.",
                    429,
                )
            hits.append(now)
            # Forget idle clients so the table cannot grow without bound.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
_jobs = threading.BoundedSemaphore(max(1, settings.max_concurrent_jobs))


@contextmanager
def job_slot(wait_seconds: float = 30) -> Iterator[None]:
    """Run a heavy job only when a slot is free; fail politely if busy."""
    if not _jobs.acquire(timeout=wait_seconds):
        raise SherlockError(
            "server_busy", "Sherlock is busy with other files right now. Please try again shortly.", 503
        )
    try:
        yield
    finally:
        _jobs.release()
