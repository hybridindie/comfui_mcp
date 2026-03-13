"""Tests for custom node management tools (tools/nodes.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.node_manager import ComfyUIManagerDetector, ComfyUIManagerUnavailableError
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.tools.nodes import register_node_tools

BASE = "http://test-comfyui:8188"


@pytest.fixture
async def components(tmp_path):
    client = ComfyUIClient(base_url=BASE)
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    wf_limiter = RateLimiter(max_per_minute=60)
    read_limiter = RateLimiter(max_per_minute=60)
    node_manager = ComfyUIManagerDetector(client)
    node_auditor = NodeAuditor()
    yield {
        "client": client,
        "audit": audit,
        "wf_limiter": wf_limiter,
        "read_limiter": read_limiter,
        "node_manager": node_manager,
        "node_auditor": node_auditor,
        "tmp_path": tmp_path,
    }


@pytest.fixture
def registered_tools(components):
    mcp = FastMCP("test")
    # Patch require_available to be a no-op so tests don't probe /manager/version
    components["node_manager"].require_available = AsyncMock()
    tools = register_node_tools(
        mcp=mcp,
        client=components["client"],
        audit=components["audit"],
        wf_limiter=components["wf_limiter"],
        read_limiter=components["read_limiter"],
        node_manager=components["node_manager"],
        node_auditor=components["node_auditor"],
    )
    return tools


@pytest.fixture
def unavailable_tools(components):
    """Tools where ComfyUI Manager is unavailable."""
    mcp = FastMCP("test")
    components["node_manager"].require_available = AsyncMock(
        side_effect=ComfyUIManagerUnavailableError(
            "ComfyUI Manager not detected. Install it from https://github.com/Comfy-Org/ComfyUI-Manager"
        )
    )
    tools = register_node_tools(
        mcp=mcp,
        client=components["client"],
        audit=components["audit"],
        wf_limiter=components["wf_limiter"],
        read_limiter=components["read_limiter"],
        node_manager=components["node_manager"],
        node_auditor=components["node_auditor"],
    )
    return tools


def _mock_node_list(query_match: str = "test"):
    """Mock GET /customnode/getlist with some node packs."""
    respx.get(f"{BASE}/customnode/getlist").mock(
        return_value=httpx.Response(
            200,
            json={
                "node_packs": {
                    "comfy-pack-one": {
                        "name": "Test Node Pack",
                        "description": "A test pack for unit tests",
                        "author": "tester",
                        "installed": "false",
                    },
                    "comfy-pack-two": {
                        "name": "Another Pack",
                        "description": "Unrelated pack",
                        "author": "someone",
                        "installed": "true",
                    },
                }
            },
        )
    )


def _mock_operation_success():
    """Mock the queue -> start -> poll flow for install/uninstall/update."""
    # POST to queue endpoint (install/uninstall/update) is mocked by caller
    respx.get(f"{BASE}/manager/queue/start").mock(return_value=httpx.Response(200))
    respx.get(f"{BASE}/manager/queue/status").mock(
        return_value=httpx.Response(200, json={"is_processing": False, "total": 1, "completed": 1})
    )


def _mock_restart_success(with_audit: bool = True):
    """Mock the restart flow: empty queue -> reboot -> reachable -> object_info."""
    respx.get(f"{BASE}/queue").mock(
        return_value=httpx.Response(200, json={"queue_running": [], "queue_pending": []})
    )
    respx.get(f"{BASE}/manager/reboot").mock(return_value=httpx.Response(200))
    if with_audit:
        respx.get(f"{BASE}/object_info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "KSampler": {"input": {}, "description": "Standard sampler"},
                    "CLIPTextEncode": {"input": {}, "description": "CLIP encoder"},
                },
            )
        )


def _mock_restart_busy_queue():
    """Mock restart when jobs are in the queue."""
    respx.get(f"{BASE}/queue").mock(
        return_value=httpx.Response(
            200,
            json={
                "queue_running": [["fake-job"]],
                "queue_pending": [],
            },
        )
    )


class TestSearchCustomNodes:
    @respx.mock
    async def test_returns_matching_results(self, registered_tools):
        _mock_node_list()
        result = await registered_tools["search_custom_nodes"](query="test")
        parsed = json.loads(result)
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["id"] == "comfy-pack-one"
        assert parsed["results"][0]["name"] == "Test Node Pack"
        assert parsed["query"] == "test"

    @respx.mock
    async def test_empty_results_when_no_match(self, registered_tools):
        _mock_node_list()
        result = await registered_tools["search_custom_nodes"](query="nonexistent-xyz")
        parsed = json.loads(result)
        assert parsed["results"] == []

    @respx.mock
    async def test_rate_limiter_called(self, components, registered_tools):
        _mock_node_list()
        # First call should succeed
        await registered_tools["search_custom_nodes"](query="test")
        # Exhaust the rate limiter
        limiter = components["read_limiter"]
        for _ in range(120):
            try:
                limiter.check("search_custom_nodes")
            except Exception:
                break
        # Next call should hit rate limit
        from comfyui_mcp.security.rate_limit import RateLimitError

        with pytest.raises(RateLimitError):
            await registered_tools["search_custom_nodes"](query="test")

    @respx.mock
    async def test_audit_log_written(self, components, registered_tools):
        _mock_node_list()
        await registered_tools["search_custom_nodes"](query="test")
        audit_path = components["tmp_path"] / "audit.log"
        lines = audit_path.read_text().strip().split("\n")
        # Should have "searching" and "searched" entries
        actions = [json.loads(line)["action"] for line in lines]
        assert "searching" in actions
        assert "searched" in actions

    async def test_manager_unavailable_raises(self, unavailable_tools):
        with pytest.raises(ComfyUIManagerUnavailableError, match="not detected"):
            await unavailable_tools["search_custom_nodes"](query="test")


class TestInstallCustomNode:
    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_install_no_restart(self, mock_sleep, registered_tools):
        respx.post(f"{BASE}/manager/queue/install").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        result = await registered_tools["install_custom_node"](id="comfy-pack-one", restart=False)
        assert "completed" in result.lower() or "operation completed" in result.lower()
        assert "Restart required" in result

    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_install_restart_empty_queue(self, mock_sleep, registered_tools):
        respx.post(f"{BASE}/manager/queue/install").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        _mock_restart_success(with_audit=True)
        result = await registered_tools["install_custom_node"](id="comfy-pack-one", restart=True)
        assert "restarted" in result.lower()
        assert "nodes scanned" in result.lower()

    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_install_restart_busy_queue_defers(self, mock_sleep, registered_tools):
        respx.post(f"{BASE}/manager/queue/install").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        _mock_restart_busy_queue()
        result = await registered_tools["install_custom_node"](id="comfy-pack-one", restart=True)
        assert "deferred" in result.lower()
        assert "1 job(s) in queue" in result

    async def test_validates_empty_id(self, registered_tools):
        with pytest.raises(ValueError, match="must not be empty"):
            await registered_tools["install_custom_node"](id="")

    async def test_validates_control_chars(self, registered_tools):
        with pytest.raises(ValueError, match="invalid characters"):
            await registered_tools["install_custom_node"](id="bad\x00id")

    async def test_validates_too_long_id(self, registered_tools):
        with pytest.raises(ValueError, match="must not exceed 200"):
            await registered_tools["install_custom_node"](id="x" * 201)

    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limiter_called(self, mock_sleep, components, registered_tools):
        respx.post(f"{BASE}/manager/queue/install").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        # First call succeeds
        await registered_tools["install_custom_node"](id="comfy-pack-one", restart=False)
        # Exhaust the rate limiter
        limiter = components["wf_limiter"]
        for _ in range(120):
            try:
                limiter.check("install_custom_node")
            except Exception:
                break
        from comfyui_mcp.security.rate_limit import RateLimitError

        with pytest.raises(RateLimitError):
            await registered_tools["install_custom_node"](id="comfy-pack-one", restart=False)


class TestUninstallCustomNode:
    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_uninstall_no_restart(self, mock_sleep, registered_tools):
        respx.post(f"{BASE}/manager/queue/uninstall").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        result = await registered_tools["uninstall_custom_node"](id="comfy-pack-one", restart=False)
        assert "operation completed" in result.lower()
        assert "Restart required" in result

    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_uninstall_restart_no_post_audit(self, mock_sleep, registered_tools):
        """Uninstall with restart should NOT run post-restart security audit."""
        respx.post(f"{BASE}/manager/queue/uninstall").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        # No audit: restart without object_info mock
        _mock_restart_success(with_audit=False)
        result = await registered_tools["uninstall_custom_node"](id="comfy-pack-one", restart=True)
        assert "restarted successfully" in result.lower()
        # Should NOT contain audit results
        assert "nodes scanned" not in result.lower()


class TestUpdateCustomNode:
    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_update_no_restart(self, mock_sleep, registered_tools):
        respx.post(f"{BASE}/manager/queue/update").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        result = await registered_tools["update_custom_node"](id="comfy-pack-one", restart=False)
        assert "operation completed" in result.lower()
        assert "Restart required" in result

    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_update_restart_with_audit(self, mock_sleep, registered_tools):
        """Update with restart should run post-restart security audit."""
        respx.post(f"{BASE}/manager/queue/update").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        _mock_restart_success(with_audit=True)
        result = await registered_tools["update_custom_node"](id="comfy-pack-one", restart=True)
        assert "restarted" in result.lower()
        assert "nodes scanned" in result.lower()

    @respx.mock
    @patch("comfyui_mcp.tools.nodes.asyncio.sleep", new_callable=AsyncMock)
    async def test_update_restart_audit_logged(self, mock_sleep, components, registered_tools):
        """Update with restart should write audit entries including post_restart_audit."""
        respx.post(f"{BASE}/manager/queue/update").mock(return_value=httpx.Response(200))
        _mock_operation_success()
        _mock_restart_success(with_audit=True)
        await registered_tools["update_custom_node"](id="comfy-pack-one", restart=True)
        audit_path = components["tmp_path"] / "audit.log"
        lines = audit_path.read_text().strip().split("\n")
        actions = [json.loads(line)["action"] for line in lines]
        assert "updating" in actions
        assert "reboot_initiated" in actions
        assert "post_restart_audit" in actions
        assert "completed" in actions


class TestGetCustomNodeStatus:
    @respx.mock
    async def test_returns_queue_status(self, registered_tools):
        respx.get(f"{BASE}/manager/queue/status").mock(
            return_value=httpx.Response(
                200,
                json={
                    "is_processing": True,
                    "total": 3,
                    "completed": 1,
                },
            )
        )
        result = await registered_tools["get_custom_node_status"]()
        parsed = json.loads(result)
        assert parsed["is_processing"] is True
        assert parsed["total"] == 3
        assert parsed["completed"] == 1

    @respx.mock
    async def test_rate_limiter_called(self, components, registered_tools):
        respx.get(f"{BASE}/manager/queue/status").mock(
            return_value=httpx.Response(
                200, json={"is_processing": False, "total": 0, "completed": 0}
            )
        )
        await registered_tools["get_custom_node_status"]()
        # Exhaust limiter
        limiter = components["read_limiter"]
        for _ in range(120):
            try:
                limiter.check("get_custom_node_status")
            except Exception:
                break
        from comfyui_mcp.security.rate_limit import RateLimitError

        with pytest.raises(RateLimitError):
            await registered_tools["get_custom_node_status"]()
