"""ComfyUI MCP Server entry point."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.config import Settings, load_settings
from comfyui_mcp.progress import WebSocketProgress
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
from comfyui_mcp.tools.discovery import register_discovery_tools
from comfyui_mcp.tools.files import register_file_tools
from comfyui_mcp.tools.generation import register_generation_tools
from comfyui_mcp.tools.history import register_history_tools
from comfyui_mcp.tools.jobs import register_job_tools
from comfyui_mcp.tools.workflow import register_workflow_tools


def _create_client(settings: Settings) -> ComfyUIClient:
    """Create and configure the ComfyUI client."""
    return ComfyUIClient(
        base_url=settings.comfyui.url,
        timeout_connect=settings.comfyui.timeout_connect,
        timeout_read=settings.comfyui.timeout_read,
        tls_verify=settings.comfyui.tls_verify,
    )


def _create_audit_logger(settings: Settings) -> AuditLogger:
    """Create and configure the audit logger."""
    audit_path = Path(settings.logging.audit_file).expanduser()
    return AuditLogger(audit_file=audit_path)


def _create_workflow_inspector(settings: Settings) -> WorkflowInspector:
    """Create and configure the workflow inspector."""
    return WorkflowInspector(
        mode=settings.security.mode,
        dangerous_nodes=settings.security.dangerous_nodes,
        allowed_nodes=settings.security.allowed_nodes,
    )


def _create_path_sanitizer(settings: Settings) -> PathSanitizer:
    """Create and configure the path sanitizer."""
    return PathSanitizer(
        allowed_extensions=settings.security.allowed_extensions,
        max_size_mb=settings.security.max_upload_size_mb,
    )


def _create_rate_limiters(settings: Settings) -> dict[str, RateLimiter]:
    """Create rate limiters for each category."""
    return {
        "workflow": RateLimiter(max_per_minute=settings.rate_limits.workflow),
        "generation": RateLimiter(max_per_minute=settings.rate_limits.generation),
        "file": RateLimiter(max_per_minute=settings.rate_limits.file_ops),
        "read": RateLimiter(max_per_minute=settings.rate_limits.read_only),
    }


def _register_all_tools(
    server: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    rate_limiters: dict[str, RateLimiter],
    inspector: WorkflowInspector,
    sanitizer: PathSanitizer,
    node_auditor: NodeAuditor,
    progress: WebSocketProgress,
) -> None:
    """Register all MCP tool groups with their dependencies."""
    register_discovery_tools(server, client, audit, rate_limiters["read"], sanitizer, node_auditor)
    register_history_tools(server, client, audit, rate_limiters["read"])
    register_job_tools(
        server,
        client,
        audit,
        rate_limiters["workflow"],
        read_limiter=rate_limiters["read"],
        progress=progress,
    )
    register_file_tools(server, client, audit, rate_limiters["file"], sanitizer)
    register_generation_tools(
        server,
        client,
        audit,
        rate_limiters["generation"],
        inspector,
        read_limiter=rate_limiters["read"],
        progress=progress,
    )
    register_workflow_tools(server, client, audit, rate_limiters["read"], inspector)


def _build_server(settings: Settings | None = None) -> tuple[FastMCP, Settings]:
    """Build and configure the MCP server with all tools registered."""
    if settings is None:
        settings = load_settings()

    client = _create_client(settings)
    audit = _create_audit_logger(settings)
    inspector = _create_workflow_inspector(settings)
    sanitizer = _create_path_sanitizer(settings)
    node_auditor = NodeAuditor()
    rate_limiters = _create_rate_limiters(settings)

    server_kwargs: dict = {
        "name": "ComfyUI",
        "instructions": (
            "Secure MCP server for generating images and managing workflows via ComfyUI. "
            "Use generate_image for quick text-to-image, or run_workflow for custom workflows. "
            "Use list_models and list_nodes to discover available resources. "
            "IMPORTANT: Before running custom workflows with run_workflow, always check the "
            "response "
            "for warnings about dangerous nodes or suspicious inputs. If warnings are present, "
            "inform the user and ask for confirmation before proceeding with execution."
        ),
    }

    if settings.transport.sse.enabled:
        server_kwargs["host"] = settings.transport.sse.host
        server_kwargs["port"] = settings.transport.sse.port

    server = FastMCP(**server_kwargs)

    progress = WebSocketProgress(
        client,
        timeout=float(settings.comfyui.timeout_read),
        tls_verify=settings.comfyui.tls_verify,
    )
    _register_all_tools(
        server,
        client,
        audit,
        rate_limiters,
        inspector,
        sanitizer,
        node_auditor,
        progress,
    )

    return server, settings


# Module-level server instance for import and CLI use
mcp, _settings = _build_server()


def main() -> None:
    """Run the MCP server."""
    if _settings.transport.sse.enabled:
        mcp.run(  # type: ignore[call-arg]
            transport="sse",
            host=_settings.transport.sse.host,
            port=_settings.transport.sse.port,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
