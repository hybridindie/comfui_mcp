"""File operation tools: upload_image, get_image, list_outputs."""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _extract_png_metadata(data: bytes) -> dict[str, str]:
    """Extract tEXt and zTXt metadata from PNG data.

    Returns a dict of key-value pairs from PNG text chunks.
    Returns an empty dict if the data is not valid PNG or has no text chunks.
    """
    if len(data) < 8 or data[:8] != _PNG_SIGNATURE:
        return {}

    metadata: dict[str, str] = {}
    offset = 8  # Skip PNG signature

    while offset + 8 <= len(data):
        try:
            length = struct.unpack(">I", data[offset : offset + 4])[0]
        except struct.error:
            break
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]

        if len(chunk_data) < length:
            break  # Truncated chunk

        if chunk_type == b"tEXt":
            null_idx = chunk_data.find(b"\x00")
            if null_idx > 0:
                key = chunk_data[:null_idx].decode("latin-1")
                value = chunk_data[null_idx + 1 :].decode("latin-1")
                metadata[key] = value

        elif chunk_type == b"zTXt":
            null_idx = chunk_data.find(b"\x00")
            if null_idx > 0 and null_idx + 2 <= len(chunk_data):
                key = chunk_data[:null_idx].decode("latin-1")
                # Skip compression method byte (always 0 = zlib)
                compressed = chunk_data[null_idx + 2 :]
                try:
                    value = zlib.decompress(compressed).decode("utf-8")
                    metadata[key] = value
                except (zlib.error, UnicodeDecodeError):
                    pass

        elif chunk_type == b"IEND":
            break

        # Move to next chunk: length(4) + type(4) + data(length) + crc(4)
        offset += 12 + length

    return metadata


def register_file_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    sanitizer: PathSanitizer,
) -> dict[str, Any]:
    """Register file operation tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def upload_image(filename: str, image_data: str, subfolder: str = "") -> str:
        """Upload an image to ComfyUI's input directory.

        Args:
            filename: Name for the uploaded file (e.g. 'reference.png')
            image_data: Base64-encoded image data
            subfolder: Optional subfolder within ComfyUI's input directory
        """
        limiter.check("upload_image")
        clean_name = sanitizer.validate_filename(filename)
        clean_subfolder = sanitizer.validate_subfolder(subfolder)
        raw = base64.b64decode(image_data)
        sanitizer.validate_size(len(raw))
        audit.log(
            tool="upload_image",
            action="uploading",
            extra={"filename": clean_name, "size_bytes": len(raw)},
        )
        result = await client.upload_image(raw, clean_name, clean_subfolder)
        audit.log(tool="upload_image", action="uploaded", extra={"result": result})
        return f"Uploaded {result.get('name', clean_name)} to ComfyUI input directory"

    tool_fns["upload_image"] = upload_image

    @mcp.tool()
    async def get_image(filename: str, subfolder: str = "output") -> str:
        """Download a generated image from ComfyUI.

        Args:
            filename: Name of the image file to retrieve
            subfolder: Directory to look in (default: 'output')

        Returns:
            Base64-encoded image data with content type prefix
        """
        limiter.check("get_image")
        clean_name = sanitizer.validate_filename(filename)
        clean_subfolder = sanitizer.validate_subfolder(subfolder)
        audit.log(tool="get_image", action="downloading", extra={"filename": clean_name})
        data, content_type = await client.get_image(clean_name, clean_subfolder)
        b64 = base64.b64encode(data).decode()
        return f"data:{content_type};base64,{b64}"

    tool_fns["get_image"] = get_image

    @mcp.tool()
    async def list_outputs() -> list[str]:
        """List files in ComfyUI's output directory."""
        limiter.check("list_outputs")
        audit.log(tool="list_outputs", action="called")
        history = await client.get_history()
        filenames = set()
        for entry in history.values():
            if isinstance(entry, dict):
                for outputs in entry.get("outputs", {}).values():
                    if isinstance(outputs, dict):
                        for images in outputs.get("images", []):
                            if isinstance(images, dict) and "filename" in images:
                                filenames.add(images["filename"])
        return sorted(filenames)

    tool_fns["list_outputs"] = list_outputs

    @mcp.tool()
    async def upload_mask(filename: str, mask_data: str, subfolder: str = "") -> str:
        """Upload a mask image to ComfyUI's input directory.

        Args:
            filename: Name for the uploaded mask file (e.g. 'mask.png')
            mask_data: Base64-encoded mask image data
            subfolder: Optional subfolder within ComfyUI's input directory
        """
        limiter.check("upload_mask")
        clean_name = sanitizer.validate_filename(filename)
        clean_subfolder = sanitizer.validate_subfolder(subfolder)
        raw = base64.b64decode(mask_data)
        sanitizer.validate_size(len(raw))
        audit.log(
            tool="upload_mask",
            action="uploading",
            extra={"filename": clean_name, "size_bytes": len(raw)},
        )
        result = await client.upload_mask(raw, clean_name, clean_subfolder)
        audit.log(tool="upload_mask", action="uploaded", extra={"result": result})
        return f"Uploaded mask {result.get('name', clean_name)} to ComfyUI input directory"

    tool_fns["upload_mask"] = upload_mask

    return tool_fns
