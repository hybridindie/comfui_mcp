"""Tests for job management MCP tools."""

import pytest
import httpx
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.tools.jobs import register_job_tools
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.security.rate_limit import RateLimiter


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    return client, audit, limiter


class TestGetQueue:
    @respx.mock
    async def test_returns_queue_state(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/queue").mock(
            return_value=httpx.Response(
                200, json={"queue_running": [["id1"]], "queue_pending": []}
            )
        )
        mcp = FastMCP("test")
        tools = register_job_tools(mcp, client, audit, limiter)
        result = await tools["get_queue"]()
        assert "queue_running" in result


class TestCancelJob:
    @respx.mock
    async def test_cancel_job_sends_delete(self, components):
        client, audit, limiter = components
        route = respx.post("http://test:8188/queue").mock(
            return_value=httpx.Response(200, json={})
        )
        mcp = FastMCP("test")
        tools = register_job_tools(mcp, client, audit, limiter)
        result = await tools["cancel_job"](prompt_id="abc-123")
        assert route.called


class TestInterrupt:
    @respx.mock
    async def test_interrupt_posts(self, components):
        client, audit, limiter = components
        route = respx.post("http://test:8188/interrupt").mock(
            return_value=httpx.Response(200, json={})
        )
        mcp = FastMCP("test")
        tools = register_job_tools(mcp, client, audit, limiter)
        await tools["interrupt"]()
        assert route.called


class TestGetJob:
    @respx.mock
    async def test_get_job_returns_history_item(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/history/abc-123").mock(
            return_value=httpx.Response(
                200, json={"abc-123": {"outputs": {"9": {"images": []}}}}
            )
        )
        mcp = FastMCP("test")
        tools = register_job_tools(mcp, client, audit, limiter)
        result = await tools["get_job"](prompt_id="abc-123")
        assert "abc-123" in result


class TestGetQueueStatus:
    @respx.mock
    async def test_get_queue_status_returns_exec_info(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"exec_info": {"queue_remaining": 5}})
        )
        mcp = FastMCP("test")
        tools = register_job_tools(mcp, client, audit, limiter)
        result = await tools["get_queue_status"]()
        assert "exec_info" in result


class TestClearQueue:
    @respx.mock
    async def test_clear_queue_pending(self, components):
        client, audit, limiter = components
        route = respx.post("http://test:8188/queue").mock(
            return_value=httpx.Response(200, json={})
        )
        mcp = FastMCP("test")
        tools = register_job_tools(mcp, client, audit, limiter)
        result = await tools["clear_queue"](clear_pending=True)
        assert "pending" in result.lower()
        assert route.called
