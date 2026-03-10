"""Generation tools: generate_image, run_workflow."""

from __future__ import annotations

import copy
import graphlib
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.security.rate_limit import RateLimiter

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


# Node class_types that load models, mapped to their model input key and type label
_MODEL_LOADERS: dict[str, tuple[str, str]] = {
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoint"),
    "CheckpointLoader": ("ckpt_name", "checkpoint"),
    "LoraLoader": ("lora_name", "lora"),
    "LoraLoaderModelOnly": ("lora_name", "lora"),
    "VAELoader": ("vae_name", "vae"),
    "UpscaleModelLoader": ("model_name", "upscale"),
    "ControlNetLoader": ("control_net_name", "controlnet"),
    "CLIPLoader": ("clip_name", "clip"),
    "UNETLoader": ("unet_name", "unet"),
}

_INPUT_NODE_TYPES = {"LoadImage", "LoadImageMask", "EmptyLatentImage"}
_OUTPUT_NODE_TYPES = {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveAnimatedPNG"}
_SAMPLER_NODE_TYPES = {"KSampler", "KSamplerAdvanced", "SamplerCustom"}


def _analyze_workflow(
    workflow: dict[str, Any], object_info: dict[str, Any] | None
) -> dict[str, Any]:
    """Analyze a ComfyUI workflow and return structured data."""
    if not workflow:
        return {
            "node_count": 0,
            "class_types": [],
            "flow": [],
            "models": [],
            "parameters": {},
            "pipeline": "unknown",
            "prompt_nodes": [],
            "negative_nodes": [],
        }

    # Build graph edges: child -> set of parents (dependencies)
    deps: dict[str, set[str]] = {}
    node_info: dict[str, dict[str, Any]] = {}

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs", {})
        deps.setdefault(node_id, set())

        display_name = class_type
        if object_info and class_type in object_info:
            display_name = object_info[class_type].get("display_name", class_type)

        node_info[node_id] = {
            "node_id": node_id,
            "class_type": class_type,
            "display_name": display_name,
            "inputs": inputs,
        }

        for value in inputs.values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                parent_id = value[0]
                if parent_id in workflow:
                    deps[node_id].add(parent_id)
                    deps.setdefault(parent_id, set())

    # Topological sort
    sorter = graphlib.TopologicalSorter(deps)
    try:
        sorted_ids = list(sorter.static_order())
    except graphlib.CycleError:
        sorted_ids = list(node_info.keys())

    flow = [node_info[nid] for nid in sorted_ids if nid in node_info]
    class_types = [n["class_type"] for n in flow]

    # Extract models
    models: list[dict[str, str]] = []
    for node in flow:
        ct = node["class_type"]
        if ct in _MODEL_LOADERS:
            key, model_type = _MODEL_LOADERS[ct]
            name = node["inputs"].get(key, "")
            if name:
                models.append({"name": name, "type": model_type})

    # Extract parameters from sampler and latent nodes
    parameters: dict[str, Any] = {}
    for node in flow:
        ct = node["class_type"]
        if ct in _SAMPLER_NODE_TYPES:
            for k in ("steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if k in node["inputs"]:
                    param_key = "sampler" if k == "sampler_name" else k
                    parameters[param_key] = node["inputs"][k]
        if ct == "EmptyLatentImage":
            for k in ("width", "height"):
                if k in node["inputs"]:
                    parameters[k] = node["inputs"][k]

    # Detect prompt/negative nodes
    prompt_nodes = []
    negative_nodes = []
    for node in flow:
        if node["class_type"] == "CLIPTextEncode":
            # Heuristic: if connected to a sampler's "negative" input, it's negative
            is_negative = False
            for other in flow:
                if other["class_type"] in _SAMPLER_NODE_TYPES:
                    neg_link = other["inputs"].get("negative")
                    if isinstance(neg_link, list) and neg_link[0] == node["node_id"]:
                        is_negative = True
                        break
            if is_negative:
                negative_nodes.append(node["node_id"])
            else:
                prompt_nodes.append(node["node_id"])

    # Pipeline type heuristic
    has_load_image = any(ct in _INPUT_NODE_TYPES - {"EmptyLatentImage"} for ct in class_types)
    has_empty_latent = "EmptyLatentImage" in class_types
    has_upscale = any("Upscale" in ct for ct in class_types)

    if has_load_image:
        pipeline = "img2img"
    elif has_empty_latent:
        pipeline = "txt2img"
    else:
        pipeline = "unknown"
    if has_upscale:
        pipeline = f"{pipeline} -> upscale" if pipeline != "unknown" else "upscale"

    return {
        "node_count": len(flow),
        "class_types": class_types,
        "flow": flow,
        "models": models,
        "parameters": parameters,
        "pipeline": pipeline,
        "prompt_nodes": prompt_nodes,
        "negative_nodes": negative_nodes,
    }


def register_generation_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    inspector: WorkflowInspector,
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

    return tool_fns
