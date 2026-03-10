"""Generation tools: generate_image, run_workflow, summarize_workflow."""

from __future__ import annotations

import contextlib
import copy
import json
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.workflow.validation import (
    SAMPLER_NODE_TYPES as _SAMPLER_NODE_TYPES,
)
from comfyui_mcp.workflow.validation import (
    WorkflowAnalysis,
)
from comfyui_mcp.workflow.validation import (
    analyze_workflow as _analyze_workflow,
)

MAX_WIDTH = 4096
MAX_HEIGHT = 4096
MIN_DIMENSION = 64


def _format_warnings(warnings: list[str]) -> str:
    """Format warnings for user display."""
    if not warnings:
        return ""
    return "\n⚠️ Warnings detected:\n" + "\n".join(f"  - {w}" for w in warnings)


# Default txt2img workflow — uses standard ComfyUI nodes
_DEFAULT_TXT2IMG: dict[str, dict[str, Any]] = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["4", 1]},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp", "images": ["8", 0]},
    },
}


def _build_txt2img_workflow(
    prompt: str,
    negative_prompt: str = "bad quality, blurry",
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 7.0,
    model: str = "",
) -> dict:
    """Build a txt2img workflow from parameters."""
    wf = copy.deepcopy(_DEFAULT_TXT2IMG)
    wf["6"]["inputs"]["text"] = prompt
    wf["7"]["inputs"]["text"] = negative_prompt
    wf["5"]["inputs"]["width"] = width
    wf["5"]["inputs"]["height"] = height
    wf["3"]["inputs"]["steps"] = steps
    wf["3"]["inputs"]["cfg"] = cfg
    if model:
        wf["4"]["inputs"]["ckpt_name"] = model
    return wf


def _format_summary(analysis: WorkflowAnalysis) -> str:
    """Format an analysis dict into a human-readable summary."""
    lines: list[str] = []

    node_count = analysis["node_count"]
    node_word = "node" if node_count == 1 else "nodes"
    lines.append(f"Workflow: {node_count} {node_word}")
    lines.append(f"Pipeline: {analysis['pipeline']}")

    if analysis["models"]:
        model_strs = [f"{m['name']} ({m['type']})" for m in analysis["models"]]
        lines.append(f"Models: {', '.join(model_strs)}")

    if analysis["flow"]:
        flow_parts: list[str] = []
        for node in analysis["flow"]:
            label = node["display_name"]
            # Add key inline params for specific node types
            ct = node["class_type"]
            inputs = node["inputs"]
            if ct == "EmptyLatentImage" and "width" in inputs and "height" in inputs:
                label += f"({inputs['width']}x{inputs['height']})"
            elif ct in _SAMPLER_NODE_TYPES:
                params = []
                if "steps" in inputs:
                    params.append(f"steps={inputs['steps']}")
                if "cfg" in inputs:
                    params.append(f"cfg={inputs['cfg']}")
                if params:
                    label += f"({', '.join(params)})"
            flow_parts.append(label)
        lines.append(f"Flow: {' -> '.join(flow_parts)}")

    for node_id in analysis["prompt_nodes"]:
        lines.append(f"Prompt: node {node_id} (CLIPTextEncode)")
    for node_id in analysis["negative_nodes"]:
        lines.append(f"Negative: node {node_id} (CLIPTextEncode)")

    if analysis["parameters"]:
        param_strs = [f"{k}={v}" for k, v in analysis["parameters"].items()]
        lines.append(f"Parameters: {', '.join(param_strs)}")

    return "\n".join(lines)


def register_generation_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    inspector: WorkflowInspector,
    *,
    read_limiter: RateLimiter | None = None,
) -> dict[str, Any]:
    """Register generation tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def run_workflow(workflow: str) -> str:
        """Submit an arbitrary ComfyUI workflow for execution.

        Args:
            workflow: JSON string of a ComfyUI workflow (API format).
                      Each key is a node ID, each value has 'class_type' and 'inputs'.
        """
        limiter.check("run_workflow")
        try:
            wf = json.loads(workflow)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON workflow: {e}") from e

        # Inspect the workflow
        result = inspector.inspect(wf)
        audit.log(
            tool="run_workflow",
            action="inspected",
            nodes_used=result.nodes_used,
            warnings=result.warnings,
            status="allowed",
        )

        warning_msg = _format_warnings(result.warnings)

        # Submit to ComfyUI
        response = await client.post_prompt(wf)
        prompt_id = response.get("prompt_id", "unknown")
        audit.log(tool="run_workflow", action="submitted", prompt_id=prompt_id)
        return f"Workflow submitted. prompt_id: {prompt_id}{warning_msg}"

    tool_fns["run_workflow"] = run_workflow

    @mcp.tool()
    async def generate_image(
        prompt: str,
        negative_prompt: str = "bad quality, blurry",
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg: float = 7.0,
        model: str = "",
    ) -> str:
        """Generate an image from a text prompt using a default txt2img workflow.

        Args:
            prompt: Text description of the image to generate
            negative_prompt: What to avoid in the image
            width: Image width in pixels (64-4096)
            height: Image height in pixels (64-4096)
            steps: Number of sampling steps (more = better quality, slower)
            cfg: Classifier-free guidance scale (higher = more prompt adherence)
            model: Checkpoint model name (leave empty for default)
        """
        if not MIN_DIMENSION <= width <= MAX_WIDTH:
            raise ValueError(f"width must be between {MIN_DIMENSION} and {MAX_WIDTH}")
        if not MIN_DIMENSION <= height <= MAX_HEIGHT:
            raise ValueError(f"height must be between {MIN_DIMENSION} and {MAX_HEIGHT}")
        if steps < 1 or steps > 100:
            raise ValueError("steps must be between 1 and 100")
        if cfg < 1.0 or cfg > 30.0:
            raise ValueError("cfg must be between 1.0 and 30.0")

        limiter.check("generate_image")
        wf = _build_txt2img_workflow(prompt, negative_prompt, width, height, steps, cfg, model)

        result = inspector.inspect(wf)
        audit.log(
            tool="generate_image",
            action="inspected",
            nodes_used=result.nodes_used,
            warnings=result.warnings,
            extra={"prompt": prompt, "width": width, "height": height},
        )

        warning_msg = _format_warnings(result.warnings)

        response = await client.post_prompt(wf)
        prompt_id = response.get("prompt_id", "unknown")
        audit.log(tool="generate_image", action="submitted", prompt_id=prompt_id)
        return f"Image generation started. prompt_id: {prompt_id}{warning_msg}"

    tool_fns["generate_image"] = generate_image

    @mcp.tool()
    async def summarize_workflow(workflow: str) -> str:
        """Summarize a ComfyUI workflow's structure, data flow, and key parameters.

        Parses the workflow graph, extracts models, parameters, and execution flow.
        Enriches with display names from the ComfyUI server when available.

        Args:
            workflow: JSON string of a ComfyUI workflow (API format).
                      Each key is a node ID, each value has 'class_type' and 'inputs'.
        """
        summary_limiter = read_limiter if read_limiter is not None else limiter
        summary_limiter.check("summarize_workflow")

        try:
            wf = json.loads(workflow)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON workflow: {e}") from e

        if not isinstance(wf, dict):
            raise ValueError("Workflow must be a JSON object keyed by node IDs")

        # Best-effort API enrichment
        object_info: dict[str, Any] | None = None
        with contextlib.suppress(httpx.HTTPError, OSError):
            object_info = await client.get_object_info()

        analysis = _analyze_workflow(wf, object_info)
        audit.log(
            tool="summarize_workflow",
            action="summarized",
            extra={
                "node_count": analysis["node_count"],
                "pipeline": analysis["pipeline"],
            },
        )
        return _format_summary(analysis)

    tool_fns["summarize_workflow"] = summarize_workflow

    return tool_fns
