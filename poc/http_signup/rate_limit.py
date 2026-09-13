"""A minimal, PoC-grade, per-process, per-key sliding-window rate limiter.

This exists to *demonstrate* the pattern this endpoint would need, not
to be a production-ready mitigation. See the "Rate Limiting / Abuse
Risiko" section of README.md for what is missing before real use --
most importantly, this is in-memory and per-process: it does not
coordinate across multiple replicas of the same service, and resets on
every restart/deploy.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class InMemoryRateLimiter:
    """Allows at most ``max_requests`` calls to :meth:`allow` for a given
    ``key`` within any rolling ``window_seconds`` window.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """Return True and record a hit if ``key`` is under its limit,
        otherwise return False without recording anything.

        ``now`` is exposed only so tests can control time deterministically
        instead of sleeping; production callers should never pass it.
        """
        current_time = time.monotonic() if now is None else now
        cutoff = current_time - self._window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self._max_requests:
                return False
            hits.append(current_time)
            return True
