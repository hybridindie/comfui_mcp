"""Tests for discovery MCP tools."""

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer, PathValidationError
from comfyui_mcp.tools.discovery import register_discovery_tools

_ALLOWED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".safetensors"]


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    sanitizer = PathSanitizer(allowed_extensions=_ALLOWED_EXTENSIONS)
    return client, audit, limiter, sanitizer


@pytest.fixture
def components_with_auditor(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    sanitizer = PathSanitizer(allowed_extensions=_ALLOWED_EXTENSIONS)
    auditor = NodeAuditor()
    return client, audit, limiter, sanitizer, auditor


class TestListModels:
    @respx.mock
    async def test_list_models_returns_models(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["v1.safetensors", "v2.safetensors"])
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["list_models"](folder="checkpoints")
        assert "v1.safetensors" in result


class TestListNodes:
    @respx.mock
    async def test_list_nodes_returns_node_types(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(200, json={"KSampler": {}, "CLIPTextEncode": {}})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["list_nodes"]()
        assert "KSampler" in result
        assert "CLIPTextEncode" in result


class TestListExtensions:
    @respx.mock
    async def test_list_extensions(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/extensions").mock(
            return_value=httpx.Response(200, json=["ext1", "ext2"])
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["list_extensions"]()
        assert len(result) == 2


class TestGetServerFeatures:
    @respx.mock
    async def test_get_server_features(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/features").mock(
            return_value=httpx.Response(200, json={"supports_preview_metadata": True})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["get_server_features"]()
        assert result["supports_preview_metadata"] is True


class TestListModelFolders:
    @respx.mock
    async def test_list_model_folders(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["list_model_folders"]()
        assert "checkpoints" in result
        assert "loras" in result


class TestGetModelMetadata:
    @respx.mock
    async def test_get_model_metadata(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/view_metadata/checkpoints").mock(
            return_value=httpx.Response(200, json={"filename": "model.safetensors", "size": 123456})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["get_model_metadata"]("checkpoints", "model.safetensors")
        assert result["filename"] == "model.safetensors"

    async def test_get_model_metadata_traversal_in_folder_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        with pytest.raises(PathValidationError):
            await tools["get_model_metadata"]("../etc", "model.safetensors")

    async def test_get_model_metadata_traversal_in_filename_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        with pytest.raises(PathValidationError, match="path separator"):
            await tools["get_model_metadata"]("checkpoints", "../../etc/passwd")


class TestListModelsValidation:
    async def test_list_models_traversal_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        with pytest.raises(PathValidationError):
            await tools["list_models"](folder="../secrets")

    async def test_list_models_slash_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        with pytest.raises(PathValidationError, match="path separator"):
            await tools["list_models"](folder="checkpoints/../../etc")


class TestAuditDangerousNodes:
    @respx.mock
    async def test_audit_dangerous_nodes(self, components_with_auditor):
        client, audit, limiter, sanitizer, auditor = components_with_auditor
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
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer, auditor)

        result = await tools["audit_dangerous_nodes"]()

        assert result["total_nodes"] == 4
        assert result["dangerous"]["count"] >= 1
        assert "RunPython" in [n["class"] for n in result["dangerous"]["nodes"]]

    @respx.mock
    async def test_audit_dangerous_nodes_without_auditor(self, components):
        client, audit, limiter, sanitizer = components
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
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["audit_dangerous_nodes"]()

        assert result["total_nodes"] == 2
        assert "dangerous" in result
        assert "suspicious" in result


_SYSTEM_STATS_RESPONSE = {
    "system": {
        "os": "posix",
        "comfyui_version": "0.3.10",
        "python_version": "3.12.0 (main)",
        "embedded_python": False,
        "hostname": "myserver",
    },
    "devices": [
        {
            "name": "NVIDIA RTX 4090",
            "type": "cuda",
            "index": 0,
            "vram_total": 24 * 1024 * 1024 * 1024,
            "vram_free": 20 * 1024 * 1024 * 1024,
            "torch_vram_total": 24 * 1024 * 1024 * 1024,
            "torch_vram_free": 20 * 1024 * 1024 * 1024,
        }
    ],
}

_QUEUE_RESPONSE = {
    "queue_running": [["id1", "prompt1", {}, {}, []]],
    "queue_pending": [],
}


class TestGetSystemInfo:
    @respx.mock
    async def test_returns_whitelisted_fields(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/system_stats").mock(
            return_value=httpx.Response(200, json=_SYSTEM_STATS_RESPONSE)
        )
        respx.get("http://test:8188/queue").mock(
            return_value=httpx.Response(200, json=_QUEUE_RESPONSE)
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["get_system_info"]()

        assert result["comfyui_version"] == "0.3.10"
        assert len(result["devices"]) == 1
        gpu = result["devices"][0]
        assert gpu["name"] == "NVIDIA RTX 4090"
        assert gpu["vram_total_mb"] == 24 * 1024
        assert gpu["vram_free_mb"] == 20 * 1024
        assert result["queue"]["running"] == 1
        assert result["queue"]["pending"] == 0

    @respx.mock
    async def test_strips_sensitive_fields(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/system_stats").mock(
            return_value=httpx.Response(200, json=_SYSTEM_STATS_RESPONSE)
        )
        respx.get("http://test:8188/queue").mock(
            return_value=httpx.Response(200, json=_QUEUE_RESPONSE)
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["get_system_info"]()

        # Sensitive fields must not appear at any level
        result_str = str(result)
        assert "hostname" not in result_str
        assert "python_version" not in result_str
        assert "myserver" not in result_str
        assert "3.12.0" not in result_str
        assert "os" not in result_str

    @respx.mock
    async def test_handles_missing_devices(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/system_stats").mock(
            return_value=httpx.Response(200, json={"system": {"comfyui_version": "0.3.10"}})
        )
        respx.get("http://test:8188/queue").mock(
            return_value=httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        )
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        result = await tools["get_system_info"]()

        assert result["devices"] == []
        assert result["comfyui_version"] == "0.3.10"
        assert result["queue"] == {"running": 0, "pending": 0}

    @respx.mock
    async def test_rate_limit_enforced(self, tmp_path):
        client = ComfyUIClient(base_url="http://test:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=0)
        sanitizer = PathSanitizer(allowed_extensions=_ALLOWED_EXTENSIONS)
        mcp = FastMCP("test")
        tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)

        from comfyui_mcp.security.rate_limit import RateLimitError

        with pytest.raises(RateLimitError):
            await tools["get_system_info"]()
