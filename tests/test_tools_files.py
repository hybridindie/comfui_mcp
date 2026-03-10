"""Tests for file operation MCP tools."""

import base64
import json
import struct
import zlib

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer, PathValidationError
from comfyui_mcp.tools.files import _extract_png_metadata, register_file_tools


def _build_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Build a PNG chunk: length + type + data + CRC."""
    import binascii

    chunk_body = chunk_type + data
    crc = binascii.crc32(chunk_body) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_body + struct.pack(">I", crc)


def _build_png_with_text_chunks(text_chunks: dict[str, str]) -> bytes:
    """Build a minimal valid PNG with tEXt chunks for testing."""
    png_signature = b"\x89PNG\r\n\x1a\n"

    # Minimal IHDR chunk (13 bytes of data)
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    ihdr = _build_chunk(b"IHDR", ihdr_data)

    # tEXt chunks
    text_chunks_bytes = b""
    for key, value in text_chunks.items():
        chunk_data = key.encode("latin-1") + b"\x00" + value.encode("latin-1")
        text_chunks_bytes += _build_chunk(b"tEXt", chunk_data)

    # Minimal IDAT chunk (empty compressed data)
    idat = _build_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))

    # IEND chunk
    iend = _build_chunk(b"IEND", b"")

    return png_signature + ihdr + text_chunks_bytes + idat + iend


def _build_png_with_ztxt_chunks(text_chunks: dict[str, str]) -> bytes:
    """Build a minimal valid PNG with zTXt chunks for testing."""
    png_signature = b"\x89PNG\r\n\x1a\n"

    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _build_chunk(b"IHDR", ihdr_data)

    ztxt_chunks_bytes = b""
    for key, value in text_chunks.items():
        compressed = zlib.compress(value.encode("utf-8"))
        chunk_data = key.encode("latin-1") + b"\x00" + b"\x00" + compressed
        ztxt_chunks_bytes += _build_chunk(b"zTXt", chunk_data)

    idat = _build_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = _build_chunk(b"IEND", b"")

    return png_signature + ihdr + ztxt_chunks_bytes + idat + iend


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


class TestExtractPngMetadata:
    def test_extracts_text_chunks(self):
        workflow = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        prompt = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        png_data = _build_png_with_text_chunks({"workflow": workflow, "prompt": prompt})
        result = _extract_png_metadata(png_data)
        assert "workflow" in result
        assert "prompt" in result
        assert result["workflow"] == workflow
        assert result["prompt"] == prompt

    def test_extracts_ztxt_compressed_chunks(self):
        workflow = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        png_data = _build_png_with_ztxt_chunks({"workflow": workflow})
        result = _extract_png_metadata(png_data)
        assert "workflow" in result
        assert result["workflow"] == workflow

    def test_returns_empty_for_no_metadata(self):
        png_data = _build_png_with_text_chunks({})
        result = _extract_png_metadata(png_data)
        assert result == {}

    def test_skips_ztxt_with_invalid_compression_method(self):
        """zTXt chunks with compression method != 0 should be ignored."""
        png_signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr = _build_chunk(b"IHDR", ihdr_data)
        # Build a zTXt chunk with compression method = 1 (invalid)
        key = b"workflow"
        compressed = zlib.compress(b'{"test": true}')
        chunk_data = key + b"\x00" + b"\x01" + compressed  # method=1
        ztxt = _build_chunk(b"zTXt", chunk_data)
        idat = _build_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        iend = _build_chunk(b"IEND", b"")
        png_data = png_signature + ihdr + ztxt + idat + iend
        result = _extract_png_metadata(png_data)
        assert "workflow" not in result

    def test_limits_decompressed_ztxt_size(self):
        """zTXt decompression should respect max_text_bytes limit."""
        # Create a zTXt chunk whose decompressed data exceeds 100 bytes
        large_value = "x" * 200
        png_data = _build_png_with_ztxt_chunks({"big_key": large_value})
        result = _extract_png_metadata(png_data, max_text_bytes=100)
        # The chunk should be silently skipped (decompression exceeds limit)
        assert "big_key" not in result

    def test_returns_empty_for_non_png(self):
        result = _extract_png_metadata(b"not a png file at all")
        assert result == {}

    def test_returns_empty_for_truncated_png(self):
        result = _extract_png_metadata(b"\x89PNG\r\n\x1a\n\x00")
        assert result == {}


class TestGetWorkflowFromImage:
    @respx.mock
    async def test_extracts_workflow_and_prompt(self, components):
        client, audit, limiter, sanitizer = components
        workflow_json = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        prompt_json = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        png_data = _build_png_with_text_chunks({"workflow": workflow_json, "prompt": prompt_json})
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=png_data, headers={"content-type": "image/png"}
            )
        )
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, sanitizer)
        result = await tools["get_workflow_from_image"](filename="test.png")
        assert result["workflow"] == {"1": {"class_type": "KSampler", "inputs": {}}}
        assert result["prompt"] == {"1": {"class_type": "KSampler", "inputs": {}}}
        assert "workflow" in result["message"].lower()
        assert "prompt" in result["message"].lower()

    @respx.mock
    async def test_extracts_ztxt_workflow(self, components):
        client, audit, limiter, sanitizer = components
        workflow_json = json.dumps({"1": {"class_type": "SaveImage", "inputs": {}}})
        png_data = _build_png_with_ztxt_chunks({"workflow": workflow_json})
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=png_data, headers={"content-type": "image/png"}
            )
        )
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, sanitizer)
        result = await tools["get_workflow_from_image"](filename="test.png")
        assert result["workflow"] == {"1": {"class_type": "SaveImage", "inputs": {}}}

    @respx.mock
    async def test_returns_none_when_no_metadata(self, components):
        client, audit, limiter, sanitizer = components
        png_data = _build_png_with_text_chunks({})
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=png_data, headers={"content-type": "image/png"}
            )
        )
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, sanitizer)
        result = await tools["get_workflow_from_image"](filename="test.png")
        assert result["workflow"] is None
        assert result["prompt"] is None
        assert "no workflow metadata" in result["message"].lower()

    @respx.mock
    async def test_rejects_non_png(self, components):
        client, audit, limiter, sanitizer = components
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=b"\xff\xd8\xff\xe0JFIF", headers={"content-type": "image/jpeg"}
            )
        )
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, sanitizer)
        with pytest.raises(ValueError, match="not a PNG"):
            await tools["get_workflow_from_image"](filename="photo.png")

    @respx.mock
    async def test_rejects_oversized_download(self, components):
        client, audit, limiter, _sanitizer = components
        # Create a sanitizer with a tiny max size to trigger the guard
        small_sanitizer = PathSanitizer(
            allowed_extensions=[".png", ".jpg", ".jpeg", ".webp", ".json"],
            max_size_mb=0,  # 0 MB = rejects everything
        )
        png_data = _build_png_with_text_chunks({"workflow": '{"1": {}}'})
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=png_data, headers={"content-type": "image/png"}
            )
        )
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, small_sanitizer)
        with pytest.raises(PathValidationError):
            await tools["get_workflow_from_image"](filename="test.png")

    async def test_path_traversal_blocked(self, components):
        client, audit, limiter, sanitizer = components
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, sanitizer)
        with pytest.raises(PathValidationError):
            await tools["get_workflow_from_image"](filename="../../../etc/passwd.png")

    @respx.mock
    async def test_handles_malformed_json_in_chunk(self, components):
        client, audit, limiter, sanitizer = components
        png_data = _build_png_with_text_chunks({"workflow": "not valid json{{"})
        respx.get("http://test:8188/view").mock(
            return_value=httpx.Response(
                200, content=png_data, headers={"content-type": "image/png"}
            )
        )
        mcp_server = FastMCP("test")
        tools = register_file_tools(mcp_server, client, audit, limiter, sanitizer)
        result = await tools["get_workflow_from_image"](filename="test.png")
        assert result["workflow"] is None
        assert (
            "malformed" in result["message"].lower() or "no workflow" in result["message"].lower()
        )
