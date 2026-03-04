"""Tests for rate limiting."""

import time

import pytest

from comfyui_mcp.security.rate_limit import RateLimiter, RateLimitError


class TestRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = RateLimiter(max_per_minute=5)
        for _ in range(5):
            limiter.check("test_tool")

    def test_blocks_requests_over_limit(self):
        limiter = RateLimiter(max_per_minute=2)
        limiter.check("test_tool")
        limiter.check("test_tool")
        with pytest.raises(RateLimitError):
            limiter.check("test_tool")

    def test_separate_tools_have_separate_limits(self):
        limiter = RateLimiter(max_per_minute=1)
        limiter.check("tool_a")
        limiter.check("tool_b")  # Should not raise

    def test_tokens_replenish_over_time(self):
        limiter = RateLimiter(max_per_minute=60)  # 1 per second
        # Exhaust all tokens
        for _ in range(60):
            limiter.check("test_tool")
        # Wait for a token to replenish
        time.sleep(1.1)
        limiter.check("test_tool")  # Should not raise

    def test_error_message_includes_tool_name(self):
        limiter = RateLimiter(max_per_minute=0)
        with pytest.raises(RateLimitError, match="my_tool"):
            limiter.check("my_tool")
