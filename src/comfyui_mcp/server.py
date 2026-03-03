"""ComfyUI MCP Server entry point."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.config import Settings, load_settings
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
from comfyui_mcp.tools.discovery import register_discovery_tools
from comfyui_mcp.tools.files import register_file_tools
from comfyui_mcp.tools.generation import register_generation_tools
from comfyui_mcp.tools.history import register_history_tools
from comfyui_mcp.tools.jobs import register_job_tools


def _build_server(settings: Settings | None = None) -> FastMCP:
    """Build and configure the MCP server with all tools registered."""
    if settings is None:
        settings = load_settings()

    # Initialize components
    client = ComfyUIClient(
        base_url=settings.comfyui.url,
        timeout_connect=settings.comfyui.timeout_connect,
        timeout_read=settings.comfyui.timeout_read,
        tls_verify=settings.comfyui.tls_verify,
    )

    audit_path = Path(settings.logging.audit_file).expanduser()
    audit = AuditLogger(audit_file=audit_path)

    inspector = WorkflowInspector(
        mode=settings.security.mode,
        dangerous_nodes=settings.security.dangerous_nodes,
        allowed_nodes=settings.security.allowed_nodes,
    )

    node_auditor = NodeAuditor()

    sanitizer = PathSanitizer(
        allowed_extensions=settings.security.allowed_extensions,
        max_size_mb=settings.security.max_upload_size_mb,
    )

    # Rate limiters per category
    workflow_limiter = RateLimiter(max_per_minute=settings.rate_limits.workflow)
    generation_limiter = RateLimiter(max_per_minute=settings.rate_limits.generation)
    file_limiter = RateLimiter(max_per_minute=settings.rate_limits.file_ops)
    read_limiter = RateLimiter(max_per_minute=settings.rate_limits.read_only)

    server = FastMCP(
        "ComfyUI",
        instructions=(
            "Secure MCP server for generating images and managing workflows via ComfyUI. "
            "Use generate_image for quick text-to-image, or run_workflow for custom workflows. "
            "Use list_models and list_nodes to discover available resources. "
            "IMPORTANT: Before running custom workflows with run_workflow, always check the response "
            "for warnings about dangerous nodes or suspicious inputs. If warnings are present, "
            "inform the user and ask for confirmation before proceeding with execution."
        ),
    )

    # Register all tool groups
    register_discovery_tools(server, client, audit, read_limiter, node_auditor)
    register_history_tools(server, client, audit, read_limiter)
    register_job_tools(server, client, audit, workflow_limiter)
    register_file_tools(server, client, audit, file_limiter, sanitizer)
    register_generation_tools(server, client, audit, generation_limiter, inspector)

    return server


# Module-level server instance for import and CLI use
mcp = _build_server()


def main() -> None:
    """Run the MCP server."""
    settings = load_settings()
    if settings.transport.sse.enabled:
        mcp.run(
            transport="sse",
            host=settings.transport.sse.host,
            port=settings.transport.sse.port,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
