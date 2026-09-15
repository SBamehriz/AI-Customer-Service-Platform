"""A small in process rate limiter."""

from __future__ import annotations

import time
from collections import deque

from .config import settings

_SWEEP_SECONDS = 60.0


class RateLimiter:
    """Sliding window limiter. Returns False when a caller is over the limit."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        # A plain dict, not a defaultdict, so a lookup never creates an entry.
        self._hits: dict[str, deque[float]] = {}
        self._next_sweep = time.monotonic() + _SWEEP_SECONDS

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True

        now = time.monotonic()
        if now >= self._next_sweep:
            self._sweep(now)

        cutoff = now - self.window
        hits = self._hits.get(key)
        if hits is None:
            hits = self._hits[key] = deque()
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    def _sweep(self, now: float) -> None:
        """Forget callers whose window has fully expired."""
        cutoff = now - self.window
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for key in stale:
            del self._hits[key]
        self._next_sweep = now + _SWEEP_SECONDS

    def reset(self) -> None:
        self._hits.clear()
        self._next_sweep = time.monotonic() + _SWEEP_SECONDS


widget_messages = RateLimiter(limit=20, window_seconds=60)

widget_addresses = RateLimiter(limit=60, window_seconds=60)

# Uploads are heavier than messages, so they get their own smaller allowance.
widget_uploads = RateLimiter(limit=12, window_seconds=300)

sign_in_addresses = RateLimiter(
    limit=settings.RATE_LIMIT_SIGN_IN_PER_ADDRESS,
    window_seconds=settings.RATE_LIMIT_SIGN_IN_WINDOW_SECONDS,
)
sign_in_accounts = RateLimiter(
    limit=settings.RATE_LIMIT_SIGN_IN_PER_ACCOUNT,
    window_seconds=settings.RATE_LIMIT_SIGN_IN_WINDOW_SECONDS,
)

registrations = RateLimiter(
    limit=settings.RATE_LIMIT_REGISTRATIONS,
    window_seconds=settings.RATE_LIMIT_REGISTRATIONS_WINDOW_SECONDS,
)

ALL_LIMITERS = (
    widget_messages,
    widget_addresses,
    widget_uploads,
    sign_in_addresses,
    sign_in_accounts,
    registrations,
)
