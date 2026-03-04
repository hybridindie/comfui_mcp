"""Tests for file operation MCP tools."""

import base64

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer, PathValidationError
from comfyui_mcp.tools.files import register_file_tools


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    sanitizer = PathSanitizer(
        allowed_extensions=[".png", ".jpg", ".jpeg", ".webp", ".json"],
        max_size_mb=50,
    )
    return client, audit, limiter, sanitizer


class TestUploadImage:
    @respx.mock
    async def test_upload_valid_image(self, components):
        client, audit, limiter, sanitizer = components
        respx.post("http://test:8188/upload/image").mock(
            return_value=httpx.Response(
                200, json={"name": "test.png", "subfolder": "", "type": "input"}
            )
        )
        mcp = FastMCP("test")
        tools = register_file_tools(mcp, client, audit, limiter, sanitizer)
        image_b64 = base64.b64encode(b"fake-png-data").decode()
        result = await tools["upload_image"](filename="test.png", image_data=image_b64)
        assert "test.png" in result

    async def test_upload_path_traversal_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_file_tools(mcp, client, audit, limiter, sanitizer)
        image_b64 = base64.b64encode(b"fake").decode()
        with pytest.raises(PathValidationError):
            await tools["upload_image"](filename="../../etc/passwd.png", image_data=image_b64)

    async def test_upload_bad_extension_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_file_tools(mcp, client, audit, limiter, sanitizer)
        image_b64 = base64.b64encode(b"fake").decode()
        with pytest.raises(PathValidationError):
            await tools["upload_image"](filename="malicious.py", image_data=image_b64)


class TestGetImage:
    @respx.mock
    async def test_get_image_returns_base64(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=b"image-bytes", headers={"content-type": "image/png"}
            )
        )
        mcp = FastMCP("test")
        tools = register_file_tools(mcp, client, audit, limiter, sanitizer)
        result = await tools["get_image"](filename="output.png")
        assert "base64" in result or "image" in result.lower()

    async def test_get_image_traversal_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp = FastMCP("test")
        tools = register_file_tools(mcp, client, audit, limiter, sanitizer)
        with pytest.raises(PathValidationError):
            await tools["get_image"](filename="../../../etc/shadow.png")
