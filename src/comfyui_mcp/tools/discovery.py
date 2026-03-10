"""Discovery tools: list_models, list_nodes, get_node_info, list_workflows."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer


def register_discovery_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    sanitizer: PathSanitizer,
    node_auditor: NodeAuditor | None = None,
) -> dict[str, Any]:
    """Register discovery tools and return a dict of callable functions for testing."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def list_models(folder: str = "checkpoints") -> list[str]:
        """List available models in a folder (checkpoints, loras, vae, etc.)."""
        limiter.check("list_models")
        sanitizer.validate_path_segment(folder, label="folder")
        audit.log(tool="list_models", action="called", extra={"folder": folder})
        return await client.get_models(folder)

    tool_fns["list_models"] = list_models

    @mcp.tool()
    async def list_nodes() -> list[str]:
        """List all available ComfyUI node types."""
        limiter.check("list_nodes")
        audit.log(tool="list_nodes", action="called")
        info = await client.get_object_info()
        return sorted(info.keys())

    tool_fns["list_nodes"] = list_nodes

    @mcp.tool()
    async def get_node_info(node_class: str) -> dict:
        """Get detailed information about a specific node type."""
        limiter.check("get_node_info")
        audit.log(tool="get_node_info", action="called", extra={"node_class": node_class})
        return await client.get_object_info(node_class)

    tool_fns["get_node_info"] = get_node_info

    @mcp.tool()
    async def list_workflows() -> list:
        """List available workflow templates."""
        limiter.check("list_workflows")
        audit.log(tool="list_workflows", action="called")
        return await client.get_workflow_templates()

    tool_fns["list_workflows"] = list_workflows

    @mcp.tool()
    async def list_extensions() -> list:
        """List available ComfyUI extensions."""
        limiter.check("list_extensions")
        audit.log(tool="list_extensions", action="called")
        return await client.get_extensions()

    tool_fns["list_extensions"] = list_extensions

    @mcp.tool()
    async def get_server_features() -> dict:
        """Get ComfyUI server features and capabilities."""
        limiter.check("get_server_features")
        audit.log(tool="get_server_features", action="called")
        return await client.get_features()

    tool_fns["get_server_features"] = get_server_features

    @mcp.tool()
    async def list_model_folders() -> list[str]:
        """List available model folder types (checkpoints, loras, vae, etc.)."""
        limiter.check("list_model_folders")
        audit.log(tool="list_model_folders", action="called")
        return await client.get_model_types()

    tool_fns["list_model_folders"] = list_model_folders

    @mcp.tool()
    async def get_model_metadata(folder: str, filename: str) -> dict:
        """Get metadata for a model file.

        Args:
            folder: Model folder type (checkpoints, loras, vae, etc.)
            filename: Name of the model file
        """
        limiter.check("get_model_metadata")
        sanitizer.validate_path_segment(folder, label="folder")
        sanitizer.validate_path_segment(filename, label="filename")
        audit.log(
            tool="get_model_metadata",
            action="called",
            extra={"folder": folder, "filename": filename},
        )
        return await client.get_view_metadata(folder, filename)

    tool_fns["get_model_metadata"] = get_model_metadata

    @mcp.tool()
    async def audit_dangerous_nodes() -> dict:
        """Audit all installed nodes to identify potentially dangerous ones.

        Scans for nodes that could execute arbitrary code, run shell commands,
        or access the file system. Useful for building a dangerous node blacklist.

        Returns:
            Dictionary with dangerous and suspicious node counts and lists
        """
        limiter.check("audit_dangerous_nodes")
        audit.log(tool="audit_dangerous_nodes", action="started")

        auditor = node_auditor if node_auditor else NodeAuditor()

        object_info = await client.get_object_info()
        result = auditor.audit_all_nodes(object_info)

        output = {
            "total_nodes": result.total_nodes,
            "dangerous": {
                "count": result.dangerous_count,
                "nodes": [
                    {"class": n.node_class, "reason": n.reason} for n in result.dangerous_nodes
                ],
            },
            "suspicious": {
                "count": result.suspicious_count,
                "nodes": [
                    {"class": n.node_class, "reason": n.reason} for n in result.suspicious_nodes
                ],
            },
        }

        audit.log(
            tool="audit_dangerous_nodes",
            action="completed",
            extra={
                "total": result.total_nodes,
                "dangerous": result.dangerous_count,
                "suspicious": result.suspicious_count,
            },
        )
        return output

    tool_fns["audit_dangerous_nodes"] = audit_dangerous_nodes

    return tool_fns
