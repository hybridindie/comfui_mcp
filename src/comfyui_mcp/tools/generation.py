"""Generation tools: image generation, workflow execution, and summarization."""

from __future__ import annotations

import contextlib
import copy
import json
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote

import httpx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.progress import WebSocketProgress
from comfyui_mcp.security.inspector import WorkflowBlockedError, WorkflowInspector
from comfyui_mcp.security.model_checker import ModelChecker
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
from comfyui_mcp.workflow.templates import create_from_template as _create_from_template
from comfyui_mcp.workflow.validation import INPUT_NODE_TYPES as _INPUT_NODE_TYPES
from comfyui_mcp.workflow.validation import SAMPLER_NODE_TYPES as _SAMPLER_NODE_TYPES
from comfyui_mcp.workflow.validation import WorkflowAnalysis
from comfyui_mcp.workflow.validation import analyze_workflow as _analyze_workflow

MAX_WIDTH = 4096
MAX_HEIGHT = 4096
MIN_DIMENSION = 64


def _validate_image_filename(filename: str, sanitizer: PathSanitizer | None) -> str:
    """Validate an image filename for use in workflow tools.

    Delegates to PathSanitizer when one is provided; otherwise applies minimal
    inline checks to block null bytes, absolute paths, and path traversal.
    """
    if sanitizer is not None:
        return sanitizer.validate_filename(filename)
    decoded = unquote(filename)
    if "\x00" in decoded:
        raise ValueError(f"Filename contains null byte: {filename!r}")
    norm = decoded.replace("\\\\", "/")
    if norm.startswith("/"):
        raise ValueError(f"Filename is an absolute path: {filename!r}")
    if ".." in PurePosixPath(norm).parts:
        raise ValueError(f"Filename contains path traversal: {filename!r}")
    return norm


def _format_warnings(warnings: list[str]) -> str:
    """Format warnings for user display."""
    if not warnings:
        return ""
    return "\n⚠️ Warnings detected:\n" + "\n".join(f"  - {w}" for w in warnings)


async def _submit_workflow(
    *,
    wf: dict[str, Any],
    tool_name: str,
    success_message: str,
    wait: bool,
    client: ComfyUIClient,
    audit: AuditLogger,
    inspector: WorkflowInspector,
    progress: WebSocketProgress | None,
    model_checker: ModelChecker | None = None,
    inspect_extra: dict[str, Any] | None = None,
) -> str:
    """Inspect, submit, and optionally wait for a workflow.

    Encapsulates the inspect -> audit -> submit -> wait pattern shared
    by all generation tools.
    """
    inspection = inspector.inspect(wf)
    if model_checker is not None:
        model_warnings = await model_checker.check_models(wf, client)
        if model_warnings:
            inspection.warnings.extend(model_warnings)
            if inspector.mode == "enforce":
                raise WorkflowBlockedError(f"Workflow blocked — missing models: {model_warnings}")

    log_kwargs: dict[str, Any] = {
        "tool": tool_name,
        "action": "inspected",
        "nodes_used": inspection.nodes_used,
        "warnings": inspection.warnings,
    }
    if inspect_extra:
        log_kwargs["extra"] = inspect_extra
    if model_checker is not None:
        log_kwargs["status"] = "allowed"
    await audit.async_log(**log_kwargs)

    warning_msg = _format_warnings(inspection.warnings)

    ws_client_id = progress.client_id if wait and progress is not None else None
    response = await client.post_prompt(wf, client_id=ws_client_id)
    prompt_id = response.get("prompt_id", "unknown")
    await audit.async_log(tool=tool_name, action="submitted", prompt_id=prompt_id)

    if wait and progress is not None:
        state = await progress.wait_for_completion(prompt_id)
        await audit.async_log(
            tool=tool_name,
            action="completed",
            prompt_id=prompt_id,
            extra={"status": state.status, "elapsed": state.elapsed_seconds},
        )
        result_dict = state.to_dict()
        if inspection.warnings:
            result_dict["warnings"] = inspection.warnings
        return json.dumps(result_dict)

    return f"{success_message} prompt_id: {prompt_id}{warning_msg}"


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


def _escape_mermaid_text(value: Any) -> str:
    """Escape text used in Mermaid node labels.

    HTML-escapes special characters so that user-controlled workflow values
    (model names, prompt text, etc.) cannot inject markup or break Mermaid
    diagrams in renderers that parse label content as HTML.
    The order matters: '&' must be replaced before '<'/'>' to avoid
    double-escaping.
    """
    text = str(value)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&#34;")
    return text.replace("\n", " ")


def _classify_node_style(class_type: str) -> str:
    """Map class types to Mermaid style categories."""
    if class_type in _SAMPLER_NODE_TYPES:
        return "sampler"
    if class_type in {"SaveImage", "PreviewImage", "SaveAnimatedWEBP", "SaveVideo"}:
        return "output"
    if "Encode" in class_type or class_type.endswith("Encoder"):
        return "encoder"
    if class_type in _INPUT_NODE_TYPES or "Loader" in class_type:
        return "loader"
    return "default"


def _format_node_subtitle(node: dict[str, Any]) -> str:
    """Build compact node subtitle with key parameters for diagram readability."""
    ct = node["class_type"]
    inputs = node["inputs"]
    if ct in {"CheckpointLoaderSimple", "CheckpointLoader"} and "ckpt_name" in inputs:
        return _escape_mermaid_text(inputs["ckpt_name"])
    if ct == "EmptyLatentImage" and "width" in inputs and "height" in inputs:
        return f"{inputs['width']}x{inputs['height']}"
    if ct in _SAMPLER_NODE_TYPES:
        parts: list[str] = []
        if "steps" in inputs:
            parts.append(f"steps={inputs['steps']}")
        if "cfg" in inputs:
            parts.append(f"cfg={inputs['cfg']}")
        return ", ".join(parts)
    if ct == "CLIPTextEncode" and "text" in inputs:
        text = _escape_mermaid_text(inputs["text"])
        return text if len(text) <= 48 else f"{text[:45]}..."
    return ""


def _edge_label_for_input(input_name: str) -> str:
    """Map ComfyUI input names to readable Mermaid edge labels."""
    mapping = {
        "model": "MODEL",
        "clip": "CLIP",
        "vae": "VAE",
        "positive": "CONDITIONING",
        "negative": "CONDITIONING",
        "latent_image": "LATENT",
        "samples": "LATENT",
        "image": "IMAGE",
        "images": "IMAGE",
    }
    return mapping.get(input_name, input_name.upper())


def _format_mermaid(analysis: WorkflowAnalysis) -> str:
    """Format an analysis dict as a Mermaid flowchart."""
    lines: list[str] = ["flowchart LR"]

    styles: dict[str, str] = {}
    for node in analysis["flow"]:
        node_id = node["node_id"]
        graph_id = f"n{node_id}"
        title = _escape_mermaid_text(node["display_name"])
        subtitle = _format_node_subtitle(node)
        label = f"{title}<br/>{subtitle}" if subtitle else title
        lines.append(f'    {graph_id}["{label}"]')
        styles[graph_id] = _classify_node_style(node["class_type"])

    node_ids = {n["node_id"] for n in analysis["flow"]}
    for node in analysis["flow"]:
        child_graph_id = f"n{node['node_id']}"
        for input_name, value in node["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                parent_id = value[0]
                if parent_id in node_ids:
                    parent_graph_id = f"n{parent_id}"
                    label = _edge_label_for_input(input_name)
                    lines.append(f"    {parent_graph_id} -->|{label}| {child_graph_id}")

    lines.extend(
        [
            "    classDef loader fill:#d9ebff,stroke:#1d4e89,color:#0b2239;",
            "    classDef sampler fill:#d8f3dc,stroke:#2d6a4f,color:#0b2818;",
            "    classDef encoder fill:#fde2c5,stroke:#b96a00,color:#3d2400;",
            "    classDef output fill:#ffd8d8,stroke:#a4161a,color:#3b090a;",
            "    classDef default fill:#eef1f4,stroke:#6b7280,color:#111827;",
        ]
    )
    for graph_id, style in styles.items():
        lines.append(f"    class {graph_id} {style};")

    return "\n".join(lines)


def register_generation_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    inspector: WorkflowInspector,
    *,
    read_limiter: RateLimiter | None = None,
    progress: WebSocketProgress | None = None,
    model_checker: ModelChecker | None = None,
    sanitizer: PathSanitizer | None = None,
) -> dict[str, Any]:
    """Register generation tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def run_workflow(workflow: str, wait: bool = False) -> str:
        """Submit an arbitrary ComfyUI workflow for execution.

        Args:
            workflow: JSON string of a ComfyUI workflow (API format).
                      Each key is a node ID, each value has 'class_type' and 'inputs'.
            wait: If True, block until execution completes and return structured result
                  with status, outputs, and elapsed time. If False (default), return
                  immediately with just the prompt_id.
        """
        limiter.check("run_workflow")
        try:
            wf = json.loads(workflow)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON workflow: {e}") from e

        return await _submit_workflow(
            wf=wf,
            tool_name="run_workflow",
            success_message="Workflow submitted.",
            wait=wait,
            client=client,
            audit=audit,
            inspector=inspector,
            progress=progress,
            model_checker=model_checker,
        )

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
        wait: bool = False,
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
            wait: If True, block until generation completes and return structured result.
                  If False (default), return immediately with just the prompt_id.
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

        return await _submit_workflow(
            wf=wf,
            tool_name="generate_image",
            success_message="Image generation started.",
            wait=wait,
            client=client,
            audit=audit,
            inspector=inspector,
            progress=progress,
            model_checker=model_checker,
            inspect_extra={"prompt": prompt, "width": width, "height": height},
        )

    tool_fns["generate_image"] = generate_image

    @mcp.tool()
    async def summarize_workflow(workflow: str, format: str = "text") -> str:  # noqa: A002
        """Summarize a ComfyUI workflow's structure, data flow, and key parameters.

        Parses the workflow graph, extracts models, parameters, and execution flow.
        Enriches with display names from the ComfyUI server when available.

        Args:
            workflow: JSON string of a ComfyUI workflow (API format).
                      Each key is a node ID, each value has 'class_type' and 'inputs'.
            format: Output format. "text" for human-readable summary (default),
                    "mermaid" for Mermaid flowchart markup.
        """
        summary_limiter = read_limiter if read_limiter is not None else limiter
        summary_limiter.check("summarize_workflow")

        output_format = format.lower().strip()
        if output_format not in {"text", "mermaid"}:
            raise ValueError('format must be either "text" or "mermaid"')

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
        await audit.async_log(
            tool="summarize_workflow",
            action="summarized",
            extra={
                "node_count": analysis["node_count"],
                "pipeline": analysis["pipeline"],
                "format": output_format,
            },
        )
        if output_format == "mermaid":
            return _format_mermaid(analysis)
        return _format_summary(analysis)

    tool_fns["summarize_workflow"] = summarize_workflow

    @mcp.tool()
    async def transform_image(
        image: str,
        prompt: str,
        negative_prompt: str = "bad quality, blurry",
        strength: float = 0.75,
        steps: int = 20,
        cfg: float = 7.0,
        model: str = "",
        wait: bool = False,
    ) -> str:
        """Transform an existing image using a text prompt (img2img).

        The input image must already be uploaded to ComfyUI via upload_image.

        Args:
            image: Filename of the input image in ComfyUI's input directory
            prompt: Text description guiding the transformation
            negative_prompt: What to avoid in the output image
            strength: How much to deviate from the input (0.0 = identical, 1.0 = fully reimagined)
            steps: Number of sampling steps (1-100)
            cfg: Classifier-free guidance scale (1.0-30.0)
            model: Checkpoint model name (leave empty for default)
            wait: If True, block until complete and return structured result with outputs
        """
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must be between 0.0 and 1.0")
        if steps < 1 or steps > 100:
            raise ValueError("steps must be between 1 and 100")
        if cfg < 1.0 or cfg > 30.0:
            raise ValueError("cfg must be between 1.0 and 30.0")

        limiter.check("transform_image")
        clean_image = _validate_image_filename(image, sanitizer)

        params: dict[str, Any] = {
            "image": clean_image,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "denoise": strength,
            "steps": steps,
            "cfg": cfg,
        }
        if model:
            params["model"] = model

        wf = _create_from_template("img2img", params)

        return await _submit_workflow(
            wf=wf,
            tool_name="transform_image",
            success_message="Image transformation started.",
            wait=wait,
            client=client,
            audit=audit,
            inspector=inspector,
            progress=progress,
            inspect_extra={"image": clean_image, "prompt": prompt, "strength": strength},
        )

    tool_fns["transform_image"] = transform_image

    @mcp.tool()
    async def inpaint_image(
        image: str,
        mask: str,
        prompt: str,
        negative_prompt: str = "bad quality, blurry",
        strength: float = 0.8,
        steps: int = 20,
        cfg: float = 7.0,
        model: str = "",
        wait: bool = False,
    ) -> str:
        """Inpaint regions of an image using a mask and text prompt.

        Both the input image and mask must already be uploaded via upload_image/upload_mask.
        White regions in the mask indicate areas to regenerate.

        Args:
            image: Filename of the input image in ComfyUI's input directory
            mask: Filename of the mask image (white = inpaint, black = keep)
            prompt: Text description for the inpainted region
            negative_prompt: What to avoid in the inpainted region
            strength: Inpainting strength (0.0 = keep original, 1.0 = fully regenerate)
            steps: Number of sampling steps (1-100)
            cfg: Classifier-free guidance scale (1.0-30.0)
            model: Checkpoint model name (leave empty for default)
            wait: If True, block until complete and return structured result with outputs
        """
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength must be between 0.0 and 1.0")
        if steps < 1 or steps > 100:
            raise ValueError("steps must be between 1 and 100")
        if cfg < 1.0 or cfg > 30.0:
            raise ValueError("cfg must be between 1.0 and 30.0")

        limiter.check("inpaint_image")
        clean_image = _validate_image_filename(image, sanitizer)
        clean_mask = _validate_image_filename(mask, sanitizer)

        params: dict[str, Any] = {
            "image": clean_image,
            "mask": clean_mask,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "denoise": strength,
            "steps": steps,
            "cfg": cfg,
        }
        if model:
            params["model"] = model

        wf = _create_from_template("inpaint", params)

        return await _submit_workflow(
            wf=wf,
            tool_name="inpaint_image",
            success_message="Inpainting started.",
            wait=wait,
            client=client,
            audit=audit,
            inspector=inspector,
            progress=progress,
            inspect_extra={"image": clean_image, "mask": clean_mask, "prompt": prompt},
        )

    tool_fns["inpaint_image"] = inpaint_image

    @mcp.tool()
    async def upscale_image(
        image: str,
        upscale_model: str = "RealESRGAN_x4plus.pth",
        wait: bool = False,
    ) -> str:
        """Upscale an image using a model-based upscaler.

        The input image must already be uploaded to ComfyUI via upload_image.
        The scale factor is determined by the upscale model (e.g. RealESRGAN_x4plus = 4x).

        Args:
            image: Filename of the input image in ComfyUI's input directory
            upscale_model: Name of the upscale model file (default: RealESRGAN_x4plus.pth).
                           Use list_models with folder='upscale_models' to see available models.
            wait: If True, block until complete and return structured result with outputs
        """
        limiter.check("upscale_image")
        clean_image = _validate_image_filename(image, sanitizer)

        wf = _create_from_template("upscale", {"image": clean_image, "model_name": upscale_model})

        return await _submit_workflow(
            wf=wf,
            tool_name="upscale_image",
            success_message="Upscaling started.",
            wait=wait,
            client=client,
            audit=audit,
            inspector=inspector,
            progress=progress,
            inspect_extra={"image": clean_image, "upscale_model": upscale_model},
        )

    tool_fns["upscale_image"] = upscale_image

    return tool_fns
