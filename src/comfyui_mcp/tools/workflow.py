"""Workflow composition tools: create_workflow, modify_workflow, validate_workflow."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.workflow.operations import apply_operations
from comfyui_mcp.workflow.templates import create_from_template
from comfyui_mcp.workflow.validation import validate_workflow as _validate_workflow


def register_workflow_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    inspector: WorkflowInspector,
) -> dict[str, Any]:
    """Register workflow composition tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def create_workflow(template: str, params: str = "{}") -> str:
        """Create a ComfyUI workflow from a template with optional parameter overrides.

        Available templates: txt2img, img2img, upscale, inpaint, txt2vid_animatediff, txt2vid_wan.

        Args:
            template: Template name (e.g. 'txt2img', 'img2img')
            params: Optional JSON string of parameter overrides.
                    Common params: prompt, negative_prompt, width, height,
                    steps, cfg, model, denoise.
        """
        limiter.check("create_workflow")
        try:
            param_dict = json.loads(params)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON params: {e}") from e

        if not isinstance(param_dict, dict):
            raise ValueError('params must be a JSON object (e.g. {"key": "value"})')

        wf = create_from_template(template, param_dict)
        audit.log(
            tool="create_workflow",
            action="created",
            extra={"template": template, "node_count": len(wf)},
        )
        return json.dumps(wf)

    tool_fns["create_workflow"] = create_workflow

    @mcp.tool()
    async def modify_workflow(workflow: str, operations: str) -> str:
        """Apply batch operations to a ComfyUI workflow.

        Operations: add_node, remove_node, set_input, connect, disconnect.
        Operations execute sequentially. If any fails, the workflow is unchanged.

        Args:
            workflow: JSON string of the workflow to modify.
            operations: JSON string of an array of operation objects.
                        Each has an 'op' field and operation-specific fields.
                        Example: [{"op": "add_node", "class_type": "LoraLoader"},
                                  {"op": "connect", "from_node": "1", "from_output": 0,
                                   "to_node": "3", "to_input": "model"}]
        """
        limiter.check("modify_workflow")
        try:
            wf = json.loads(workflow)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON workflow: {e}") from e

        if not isinstance(wf, dict):
            raise ValueError("Workflow must be a JSON object keyed by node IDs")

        try:
            ops = json.loads(operations)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON operations: {e}") from e

        if not isinstance(ops, list) or not all(isinstance(op, dict) for op in ops):
            raise ValueError("Operations must be a JSON array of operation objects")

        result = apply_operations(wf, ops)
        audit.log(
            tool="modify_workflow",
            action="modified",
            extra={"operations": len(ops), "node_count": len(result)},
        )
        return json.dumps(result)

    tool_fns["modify_workflow"] = modify_workflow

    @mcp.tool()
    async def validate_workflow(workflow: str) -> str:
        """Validate a ComfyUI workflow for structural correctness and security.

        Checks: node structure, connection references, installed node types,
        available models, dangerous nodes, and suspicious inputs.

        Args:
            workflow: JSON string of the workflow to validate.

        Returns:
            JSON string with: valid (bool), errors (list), warnings (list),
            node_count (int), pipeline (str).
        """
        limiter.check("validate_workflow")
        try:
            wf = json.loads(workflow)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON workflow: {e}") from e

        if not isinstance(wf, dict):
            raise ValueError("Workflow must be a JSON object keyed by node IDs")

        result = await _validate_workflow(wf, client, inspector)
        audit.log(
            tool="validate_workflow",
            action="validated",
            extra={
                "valid": result["valid"],
                "error_count": len(result["errors"]),
                "warning_count": len(result["warnings"]),
            },
        )
        return json.dumps(result)

    tool_fns["validate_workflow"] = validate_workflow

    return tool_fns
