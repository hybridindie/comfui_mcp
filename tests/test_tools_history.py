"""Tests for history MCP tools."""

import httpx
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.tools.history import register_history_tools
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.security.rate_limit import RateLimiter

import pytest


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    return client, audit, limiter


class TestGetHistory:
    @respx.mock
    async def test_returns_history(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/history").mock(
            return_value=httpx.Response(200, json={"abc": {"outputs": {}}})
        )
        mcp = FastMCP("test")
        tools = register_history_tools(mcp, client, audit, limiter)
        result = await tools["get_history"]()
        assert "abc" in result
