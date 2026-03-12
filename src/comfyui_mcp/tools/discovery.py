"""Discovery tools: list_models, list_nodes, get_node_info, list_workflows."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer

_SUPPORTED_MODEL_FAMILIES = {"sd15", "sdxl", "flux", "sd3", "cascade"}

_MODEL_FAMILY_ALIASES = {
    "sd1.5": "sd15",
    "sd 1.5": "sd15",
    "stable-diffusion-1.5": "sd15",
    "stable diffusion 1.5": "sd15",
    "stable_diffusion_1_5": "sd15",
    "stable-diffusion-xl": "sdxl",
    "stable diffusion xl": "sdxl",
    "stable_diffusion_xl": "sdxl",
    "flux.1": "flux",
    "sd3.5": "sd3",
    "stable-cascade": "cascade",
}

_MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "sd15": {
        "recommended": {
            "sampler": "euler_ancestral",
            "scheduler": "normal",
            "steps": 28,
            "cfg": 7.0,
            "resolution": "512x768",
            "clip_skip": 1,
            "notes": "Tag-heavy prompts and negative prompts work well.",
        }
    },
    "sdxl": {
        "recommended": {
            "sampler": "dpmpp_2m",
            "scheduler": "karras",
            "steps": 30,
            "cfg": 5.5,
            "resolution": "1024x1024",
            "clip_skip": 1,
            "notes": "Prefer natural language prompts with clear scene composition.",
        }
    },
    "flux": {
        "recommended": {
            "sampler": "euler",
            "scheduler": "simple",
            "steps": 20,
            "cfg": 1.0,
            "resolution": "1024x1024",
            "clip_skip": 1,
            "notes": "Flow-matching models expect low CFG and concise language.",
        }
    },
    "sd3": {
        "recommended": {
            "sampler": "dpmpp_2m",
            "scheduler": "sgm_uniform",
            "steps": 28,
            "cfg": 4.5,
            "resolution": "1024x1024",
            "clip_skip": 1,
            "notes": "Use detailed, descriptive prompts; avoid over-weighting terms.",
        }
    },
    "cascade": {
        "recommended": {
            "sampler": "dpmpp_2m",
            "scheduler": "simple",
            "steps": 24,
            "cfg": 4.0,
            "resolution": "1024x1024",
            "clip_skip": 1,
            "notes": "Cascade benefits from broad composition instructions first.",
        }
    },
}

_PROMPTING_GUIDES: dict[str, dict[str, Any]] = {
    "sd15": {
        "prompt_structure": "subject, style, lighting, lens/composition, quality tags",
        "weight_syntax": "(token:1.2)",
        "quality_tags": ["masterpiece", "best quality", "high detail"],
        "negative_prompt_tips": "Use negatives for anatomy artifacts and low-quality tokens.",
    },
    "sdxl": {
        "prompt_structure": "subject + environment + mood + camera framing",
        "weight_syntax": "(token:1.1)",
        "quality_tags": ["cinematic lighting", "high detail", "sharp focus"],
        "negative_prompt_tips": "Keep negatives shorter than SD1.5 to avoid over-constraining.",
    },
    "flux": {
        "prompt_structure": "natural language sentence describing subject, setting, and style",
        "weight_syntax": "Avoid heavy weighting unless necessary",
        "quality_tags": ["natural lighting", "detailed texture"],
        "negative_prompt_tips": "Use short negatives only for hard constraints (e.g. watermark).",
    },
    "sd3": {
        "prompt_structure": "clear scene description with explicit style and camera intent",
        "weight_syntax": "Light weighting only; rely on plain language first",
        "quality_tags": ["balanced composition", "fine detail"],
        "negative_prompt_tips": (
            "Use focused negatives for specific defects, not long keyword lists."
        ),
    },
    "cascade": {
        "prompt_structure": "high-level composition first, then style modifiers",
        "weight_syntax": "(token:1.1) for minor emphasis",
        "quality_tags": ["clean composition", "color harmony"],
        "negative_prompt_tips": "Keep negatives concise; tune guidance before adding many tokens.",
    },
}


def _normalize_model_family(model_family: str) -> str:
    key = model_family.strip().lower()
    return _MODEL_FAMILY_ALIASES.get(key, key)


def _infer_model_family(model_name: str) -> str | None:
    name = model_name.strip().lower()
    checks = [
        ("flux", "flux"),
        ("sdxl", "sdxl"),
        ("sd3", "sd3"),
        ("cascade", "cascade"),
        ("dreamshaper", "sd15"),
        ("anything", "sd15"),
    ]
    for needle, family in checks:
        if needle in name:
            return family
    return None


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

    @mcp.tool()
    async def get_system_info() -> dict:
        """Return sanitized ComfyUI system information.

        Returns a whitelist-filtered subset of system stats useful for making
        generation decisions: GPU VRAM, queue depth, and ComfyUI version.
        Sensitive fields (hostname, OS, CPU details, file paths, Python version,
        network interfaces) are deliberately excluded.

        Returns:
            Dictionary with keys: comfyui_version, devices (list of GPU info),
            queue (running/pending counts).
        """
        limiter.check("get_system_info")
        audit.log(tool="get_system_info", action="called")

        raw = await client.get_system_stats()
        queue_raw = await client.get_queue()

        # Whitelist: only forward fields that are safe to expose
        devices: list[dict] = []
        for device in raw.get("devices", []):
            if not isinstance(device, dict):
                continue
            entry: dict = {}
            if "name" in device:
                entry["name"] = str(device["name"])
            vram_total = device.get("vram_total")
            vram_free = device.get("vram_free")
            if isinstance(vram_total, int | float):
                entry["vram_total_mb"] = round(vram_total / (1024 * 1024))
            if isinstance(vram_free, int | float):
                entry["vram_free_mb"] = round(vram_free / (1024 * 1024))
            if "torch_vram_total" in device and isinstance(device["torch_vram_total"], int | float):
                entry["torch_vram_total_mb"] = round(device["torch_vram_total"] / (1024 * 1024))
            if "torch_vram_free" in device and isinstance(device["torch_vram_free"], int | float):
                entry["torch_vram_free_mb"] = round(device["torch_vram_free"] / (1024 * 1024))
            if entry:
                devices.append(entry)

        running = len(queue_raw.get("queue_running", []))
        pending = len(queue_raw.get("queue_pending", []))

        result: dict = {
            "comfyui_version": str(raw.get("system", {}).get("comfyui_version", "unknown")),
            "devices": devices,
            "queue": {"running": running, "pending": pending},
        }
        return result

    tool_fns["get_system_info"] = get_system_info

    @mcp.tool()
    async def get_model_presets(
        model_name: str | None = None,
        model_family: str | None = None,
    ) -> dict[str, Any]:
        """Return recommended generation presets for a model family.

        Args:
            model_name: Optional model filename to infer family from.
            model_family: Optional explicit family (sd15, sdxl, flux, sd3, cascade).

        Returns:
            Dictionary containing normalized family and recommended settings.
        """
        limiter.check("get_model_presets")
        audit.log(
            tool="get_model_presets",
            action="called",
            extra={"model_name": model_name, "model_family": model_family},
        )

        family: str | None = None
        if model_family:
            family = _normalize_model_family(model_family)
        elif model_name:
            family = _infer_model_family(model_name)
            if family is None:
                raise ValueError(f"Could not infer model family from: {model_name}")
        else:
            raise ValueError("Provide either model_name or model_family")

        if family not in _SUPPORTED_MODEL_FAMILIES:
            supported = ", ".join(sorted(_SUPPORTED_MODEL_FAMILIES))
            raise ValueError(f"Unknown model family: {family}. Supported families: {supported}")

        return {
            "family": family,
            **_MODEL_PRESETS[family],
        }

    tool_fns["get_model_presets"] = get_model_presets

    @mcp.tool()
    async def get_prompting_guide(model_family: str) -> dict[str, Any]:
        """Return prompt-engineering guidance for a model family.

        Args:
            model_family: Family name (sd15, sdxl, flux, sd3, cascade).
        """
        limiter.check("get_prompting_guide")
        normalized = _normalize_model_family(model_family)
        audit.log(
            tool="get_prompting_guide",
            action="called",
            extra={"model_family": normalized},
        )

        if normalized not in _SUPPORTED_MODEL_FAMILIES:
            supported = ", ".join(sorted(_SUPPORTED_MODEL_FAMILIES))
            raise ValueError(f"Unknown model family: {normalized}. Supported families: {supported}")

        return {
            "family": normalized,
            "guide": _PROMPTING_GUIDES[normalized],
        }

    tool_fns["get_prompting_guide"] = get_prompting_guide

    return tool_fns
