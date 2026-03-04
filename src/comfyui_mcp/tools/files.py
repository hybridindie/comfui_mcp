"""File operation tools: upload_image, get_image, list_outputs."""

from __future__ import annotations

import base64
from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer


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
