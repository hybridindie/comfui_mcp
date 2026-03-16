"""Custom node management tools backed by ComfyUI Manager."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.node_manager import ComfyUIManagerDetector
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

_QUEUE_POLL_INTERVAL = 2
_QUEUE_POLL_TIMEOUT = 300
_RESTART_POLL_INTERVAL = 3
_RESTART_POLL_TIMEOUT = 60
_RESTART_SETTLE_DELAY = 5
_MAX_SEARCH_RESULTS = 10


def _validate_node_id(node_id: str) -> str:
    """Validate a node pack ID."""
    if not node_id:
        raise ValueError("id must not be empty")
    if len(node_id) > 200:
        raise ValueError("id must not exceed 200 characters")
    if _CONTROL_CHAR_RE.search(node_id):
        raise ValueError(f"id contains invalid characters: {node_id!r}")
    return node_id


async def _poll_queue_completion(client: ComfyUIClient) -> str | None:
    """Poll the Manager queue until processing completes.

    Returns None on success, message on timeout.
    """
    elapsed = 0.0
    while elapsed < _QUEUE_POLL_TIMEOUT:
        status = await client.get_custom_node_queue_status()
        if not status.get("is_processing", False):
            return None
        await asyncio.sleep(_QUEUE_POLL_INTERVAL)
        elapsed += _QUEUE_POLL_INTERVAL
    return "Operation queued but not yet complete. Use `get_custom_node_status` to check progress."


async def _handle_restart(
    client: ComfyUIClient,
    node_auditor: NodeAuditor,
    audit: AuditLogger,
    tool_name: str,
    run_audit: bool,
) -> str:
    """Check queue safety, reboot, wait for availability, optionally audit."""
    # Check ComfyUI job queue before rebooting
    queue = await client.get_queue()
    running = queue.get("queue_running", [])
    pending = queue.get("queue_pending", [])
    active_count = len(running) + len(pending)
    if active_count > 0:
        return (
            f" Restart deferred — {active_count} job(s) in queue. "
            "Restart manually, then run `audit_dangerous_nodes`."
        )

    await client.reboot_comfyui()
    await audit.async_log(tool=tool_name, action="reboot_initiated")

    # Poll until ComfyUI is reachable again
    elapsed = 0.0
    reachable = False
    while elapsed < _RESTART_POLL_TIMEOUT:
        await asyncio.sleep(_RESTART_POLL_INTERVAL)
        elapsed += _RESTART_POLL_INTERVAL
        try:
            await client.get_queue()
            reachable = True
            break
        except (httpx.RequestError, httpx.HTTPStatusError):
            continue

    if not reachable:
        return " ComfyUI restarting — not yet reachable. Check back shortly."

    # Wait for node loading to complete
    await asyncio.sleep(_RESTART_SETTLE_DELAY)

    if not run_audit:
        return " ComfyUI restarted successfully."

    # Post-restart security audit
    try:
        object_info = await client.get_object_info()
        audit_result = node_auditor.audit_all_nodes(object_info)
        await audit.async_log(
            tool=tool_name,
            action="post_restart_audit",
            extra={
                "total_nodes": audit_result.total_nodes,
                "dangerous_count": audit_result.dangerous_count,
                "suspicious_count": audit_result.suspicious_count,
            },
        )
        if audit_result.dangerous_count > 0 or audit_result.suspicious_count > 0:
            findings = []
            for node in audit_result.dangerous_nodes:
                findings.append(f"  DANGEROUS: {node.node_class} — {node.reason}")
            for node in audit_result.suspicious_nodes:
                findings.append(f"  SUSPICIOUS: {node.node_class} — {node.reason}")
            return (
                f" ComfyUI restarted. Security audit: {audit_result.total_nodes} nodes scanned, "
                f"{audit_result.dangerous_count} dangerous, "
                f"{audit_result.suspicious_count} suspicious.\n" + "\n".join(findings)
            )
        return (
            f" ComfyUI restarted. Security audit: {audit_result.total_nodes} nodes scanned, "
            "no dangerous patterns found."
        )
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        return f" ComfyUI restarted but audit failed: {e}"


async def _execute_node_operation(
    *,
    client: ComfyUIClient,
    action_fn: Any,
    node_id: str,
    version: str,
    restart: bool,
    node_auditor: NodeAuditor,
    audit: AuditLogger,
    tool_name: str,
    run_post_audit: bool,
) -> str:
    """Shared queue→start→poll→restart+audit flow for install/uninstall/update."""
    await action_fn(node_id, version)
    await client.start_custom_node_queue()

    timeout_msg = await _poll_queue_completion(client)
    if timeout_msg:
        return timeout_msg

    result = f"Node pack '{node_id}' operation completed."

    if restart:
        restart_msg = await _handle_restart(
            client, node_auditor, audit, tool_name, run_audit=run_post_audit
        )
        result += restart_msg
    else:
        result += " Restart required for nodes to become active."

    return result


def register_node_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    wf_limiter: RateLimiter,
    read_limiter: RateLimiter,
    node_manager: ComfyUIManagerDetector,
    node_auditor: NodeAuditor,
) -> dict[str, Any]:
    """Register custom node management tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def search_custom_nodes(query: str) -> str:
        """Search the ComfyUI Manager registry for custom nodes.

        Args:
            query: Search term to match against node pack name, description, or author.

        Returns:
            JSON with matching node packs including name, description, author,
            install status, and ID (for use with install_custom_node).
        """
        read_limiter.check("search_custom_nodes")
        await node_manager.require_available()

        await audit.async_log(
            tool="search_custom_nodes",
            action="searching",
            extra={"query": query},
        )

        data = await client.get_custom_node_list(mode="remote")
        node_packs = data.get("node_packs", {})

        query_lower = query.lower()
        results: list[dict[str, str]] = []
        for pack_id, pack_info in node_packs.items():
            if not isinstance(pack_info, dict):
                continue
            name = pack_info.get("name", "")
            description = pack_info.get("description", "")
            author = pack_info.get("author", "")
            searchable = f"{name} {description} {author}".lower()
            if query_lower in searchable:
                results.append(
                    {
                        "id": pack_id,
                        "name": name,
                        "description": description,
                        "author": author,
                        "installed": pack_info.get("installed", "false"),
                    }
                )
            if len(results) >= _MAX_SEARCH_RESULTS:
                break

        await audit.async_log(
            tool="search_custom_nodes",
            action="searched",
            extra={"query": query, "result_count": len(results)},
        )

        return json.dumps({"results": results, "query": query})

    tool_fns["search_custom_nodes"] = search_custom_nodes

    @mcp.tool()
    async def install_custom_node(
        id: str,  # noqa: A002
        version: str = "",
        restart: bool = False,
    ) -> str:
        """Install a custom node pack from the ComfyUI Manager registry.

        Args:
            id: Node pack ID from the registry (use search_custom_nodes to find IDs).
            version: Specific version to install (empty string = latest).
            restart: If True, restart ComfyUI after install and run a security audit
                     on all installed nodes. If False, manual restart is needed.

        Returns:
            Status message. If restart=True, includes security audit results.
        """
        wf_limiter.check("install_custom_node")
        await node_manager.require_available()
        _validate_node_id(id)

        await audit.async_log(
            tool="install_custom_node",
            action="installing",
            extra={"id": id, "version": version},
        )

        result = await _execute_node_operation(
            client=client,
            action_fn=client.queue_custom_node_install,
            node_id=id,
            version=version,
            restart=restart,
            node_auditor=node_auditor,
            audit=audit,
            tool_name="install_custom_node",
            run_post_audit=True,
        )

        await audit.async_log(
            tool="install_custom_node",
            action="completed",
            extra={"id": id, "version": version, "restart": restart},
        )

        return result

    tool_fns["install_custom_node"] = install_custom_node

    @mcp.tool()
    async def uninstall_custom_node(
        id: str,  # noqa: A002
        restart: bool = False,
    ) -> str:
        """Uninstall a custom node pack.

        Args:
            id: Node pack ID to uninstall.
            restart: If True, restart ComfyUI after uninstall.

        Returns:
            Status message.
        """
        wf_limiter.check("uninstall_custom_node")
        await node_manager.require_available()
        _validate_node_id(id)

        await audit.async_log(
            tool="uninstall_custom_node",
            action="uninstalling",
            extra={"id": id},
        )

        result = await _execute_node_operation(
            client=client,
            action_fn=client.queue_custom_node_uninstall,
            node_id=id,
            version="",
            restart=restart,
            node_auditor=node_auditor,
            audit=audit,
            tool_name="uninstall_custom_node",
            run_post_audit=False,
        )

        await audit.async_log(
            tool="uninstall_custom_node",
            action="completed",
            extra={"id": id, "restart": restart},
        )

        return result

    tool_fns["uninstall_custom_node"] = uninstall_custom_node

    @mcp.tool()
    async def update_custom_node(
        id: str,  # noqa: A002
        restart: bool = False,
    ) -> str:
        """Update a custom node pack to the latest version.

        Args:
            id: Node pack ID to update.
            restart: If True, restart ComfyUI after update and run a security audit
                     on all installed nodes.

        Returns:
            Status message. If restart=True, includes security audit results.
        """
        wf_limiter.check("update_custom_node")
        await node_manager.require_available()
        _validate_node_id(id)

        await audit.async_log(
            tool="update_custom_node",
            action="updating",
            extra={"id": id},
        )

        result = await _execute_node_operation(
            client=client,
            action_fn=client.queue_custom_node_update,
            node_id=id,
            version="",
            restart=restart,
            node_auditor=node_auditor,
            audit=audit,
            tool_name="update_custom_node",
            run_post_audit=True,
        )

        await audit.async_log(
            tool="update_custom_node",
            action="completed",
            extra={"id": id, "restart": restart},
        )

        return result

    tool_fns["update_custom_node"] = update_custom_node

    @mcp.tool()
    async def get_custom_node_status() -> str:
        """Check the custom node operation queue status.

        Returns:
            JSON with queue status: total tasks, completed, in progress, and
            whether the queue is currently processing.
        """
        read_limiter.check("get_custom_node_status")
        await node_manager.require_available()

        await audit.async_log(tool="get_custom_node_status", action="checking")

        status = await client.get_custom_node_queue_status()

        await audit.async_log(
            tool="get_custom_node_status",
            action="checked",
            extra={"status": status},
        )

        return json.dumps(status)

    tool_fns["get_custom_node_status"] = get_custom_node_status

    return tool_fns
