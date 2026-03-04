"""Job management tools: get_queue, get_job, cancel_job, interrupt."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.rate_limit import RateLimiter


def register_job_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
) -> dict[str, Any]:
    """Register job management tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def get_queue() -> dict:
        """Get the current ComfyUI execution queue state."""
        limiter.check("get_queue")
        audit.log(tool="get_queue", action="called")
        return await client.get_queue()

    tool_fns["get_queue"] = get_queue

    @mcp.tool()
    async def get_job(prompt_id: str) -> dict:
        """Check the status of a specific job by its prompt_id."""
        limiter.check("get_job")
        audit.log(tool="get_job", action="called", extra={"prompt_id": prompt_id})
        return await client.get_history_item(prompt_id)

    tool_fns["get_job"] = get_job

    @mcp.tool()
    async def cancel_job(prompt_id: str) -> str:
        """Cancel a running or queued job by its prompt_id."""
        limiter.check("cancel_job")
        audit.log(tool="cancel_job", action="called", extra={"prompt_id": prompt_id})
        await client.delete_queue_item(prompt_id)
        return f"Cancelled job {prompt_id}"

    tool_fns["cancel_job"] = cancel_job

    @mcp.tool()
    async def interrupt() -> str:
        """Interrupt the currently executing workflow."""
        limiter.check("interrupt")
        audit.log(tool="interrupt", action="called")
        await client.interrupt()
        return "Interrupted current execution"

    tool_fns["interrupt"] = interrupt

    @mcp.tool()
    async def get_queue_status() -> dict:
        """Get detailed queue status including currently running and pending prompts."""
        limiter.check("get_queue_status")
        audit.log(tool="get_queue_status", action="called")
        return await client.get_prompt_status()

    tool_fns["get_queue_status"] = get_queue_status

    @mcp.tool()
    async def clear_queue(clear_running: bool = False, clear_pending: bool = True) -> str:
        """Clear items from the execution queue.

        Args:
            clear_running: Stop the currently running workflow
            clear_pending: Remove pending workflows from the queue
        """
        limiter.check("clear_queue")
        audit.log(
            tool="clear_queue",
            action="called",
            extra={"clear_running": clear_running, "clear_pending": clear_pending},
        )
        await client.clear_queue(clear_running=clear_running, clear_pending=clear_pending)
        return f"Queue cleared (running={clear_running}, pending={clear_pending})"

    tool_fns["clear_queue"] = clear_queue

    return tool_fns
