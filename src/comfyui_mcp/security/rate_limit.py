"""Token-bucket rate limiter for MCP tools."""

from __future__ import annotations

import time


class RateLimitError(Exception):
    """Raised when a tool exceeds its rate limit."""


class _Bucket:
    __slots__ = ("_last_refill", "_max_tokens", "_refill_rate", "_tokens")

    def __init__(self, max_per_minute: int) -> None:
        self._max_tokens = float(max_per_minute)
        self._tokens = float(max_per_minute)
        self._refill_rate = max_per_minute / 60.0  # tokens per second
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class RateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self._max_per_minute = max_per_minute
        self._buckets: dict[str, _Bucket] = {}

    def check(self, tool_name: str) -> None:
        """Check rate limit for a tool. Raises RateLimitError if over limit."""
        if tool_name not in self._buckets:
            self._buckets[tool_name] = _Bucket(self._max_per_minute)

        if not self._buckets[tool_name].consume():
            raise RateLimitError(
                f"Rate limit exceeded for tool '{tool_name}'. "
                f"Max {self._max_per_minute} requests/minute."
            )
