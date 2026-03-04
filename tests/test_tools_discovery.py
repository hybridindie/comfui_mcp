"""Tests for discovery MCP tools."""

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.tools.discovery import register_discovery_tools


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    return client, audit, limiter


@pytest.fixture
def components_with_auditor(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    auditor = NodeAuditor()
    return client, audit, limiter, auditor


class TestListModels:
    @respx.mock
    async def test_list_models_returns_models(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["v1.safetensors", "v2.safetensors"])
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["list_models"](folder="checkpoints")
        assert "v1.safetensors" in result


class TestListNodes:
    @respx.mock
    async def test_list_nodes_returns_node_types(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(200, json={"KSampler": {}, "CLIPTextEncode": {}})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["list_nodes"]()
        assert "KSampler" in result
        assert "CLIPTextEncode" in result


class TestListExtensions:
    @respx.mock
    async def test_list_extensions(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/extensions").mock(
            return_value=httpx.Response(200, json=["ext1", "ext2"])
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["list_extensions"]()
        assert len(result) == 2


class TestGetServerFeatures:
    @respx.mock
    async def test_get_server_features(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/features").mock(
            return_value=httpx.Response(200, json={"supports_preview_metadata": True})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["get_server_features"]()
        assert result["supports_preview_metadata"] is True


class TestListModelFolders:
    @respx.mock
    async def test_list_model_folders(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["list_model_folders"]()
        assert "checkpoints" in result
        assert "loras" in result


class TestGetModelMetadata:
    @respx.mock
    async def test_get_model_metadata(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/view_metadata/checkpoints").mock(
            return_value=httpx.Response(200, json={"filename": "model.safetensors", "size": 123456})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["get_model_metadata"]("checkpoints", "model.safetensors")
        assert result["filename"] == "model.safetensors"


class TestAuditDangerousNodes:
    @respx.mock
    async def test_audit_dangerous_nodes(self, components_with_auditor):
        client, audit, limiter, auditor = components_with_auditor
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "KSampler": {"input": {}},
                    "RunPython": {"input": {"code": {"type": "CODE"}}},
                    "ShellCommand": {"input": {}},
                    "CLIPTextEncode": {"input": {"text": {"type": "STRING"}}},
                },
            )
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, auditor)

        result = await tools["audit_dangerous_nodes"]()

        assert result["total_nodes"] == 4
        assert result["dangerous"]["count"] >= 1
        assert "RunPython" in [n["class"] for n in result["dangerous"]["nodes"]]

    @respx.mock
    async def test_audit_dangerous_nodes_without_auditor(self, components):
        client, audit, limiter = components
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "KSampler": {"input": {}},
                    "RunPython": {"input": {}},
                },
            )
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter)

        result = await tools["audit_dangerous_nodes"]()

        assert result["total_nodes"] == 2
        assert "dangerous" in result
        assert "suspicious" in result
