"""Workflow validation: structural checks, server checks, and security inspection."""

from __future__ import annotations

import asyncio
import contextlib
import graphlib
from typing import Any, TypedDict

import httpx

from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.model_registry import MODEL_LOADER_FIELDS, get_single_field_loaders
from comfyui_mcp.security.inspector import WorkflowBlockedError, WorkflowInspector

# Derived view for analyze_workflow: single-field loaders only
_SINGLE_FIELD_LOADERS = get_single_field_loaders()

INPUT_NODE_TYPES = {"LoadImage", "LoadImageMask", "EmptyLatentImage"}
SAMPLER_NODE_TYPES = {"KSampler", "KSamplerAdvanced", "SamplerCustom"}


class WorkflowAnalysis(TypedDict):
    """Structured result from analyze_workflow."""

    node_count: int
    class_types: list[str]
    flow: list[dict[str, Any]]
    models: list[dict[str, str]]
    parameters: dict[str, Any]
    pipeline: str
    prompt_nodes: list[str]
    negative_nodes: list[str]


def analyze_workflow(
    workflow: dict[str, Any], object_info: dict[str, Any] | None = None
) -> WorkflowAnalysis:
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

    deps: dict[str, set[str]] = {}
    node_info: dict[str, dict[str, Any]] = {}

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {}
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

    sorter = graphlib.TopologicalSorter(deps)
    try:
        sorted_ids = list(sorter.static_order())
    except graphlib.CycleError:
        sorted_ids = list(node_info.keys())

    flow = [node_info[nid] for nid in sorted_ids if nid in node_info]
    class_types = [n["class_type"] for n in flow]

    models: list[dict[str, str]] = []
    for node in flow:
        ct = node["class_type"]
        if ct in _SINGLE_FIELD_LOADERS:
            key, folder = _SINGLE_FIELD_LOADERS[ct]
            name = node["inputs"].get(key, "")
            if name:
                models.append({"name": name, "type": folder})

    parameters: dict[str, Any] = {}
    for node in flow:
        ct = node["class_type"]
        if ct in SAMPLER_NODE_TYPES:
            for k in ("steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if k in node["inputs"]:
                    param_key = "sampler" if k == "sampler_name" else k
                    parameters[param_key] = node["inputs"][k]
        if ct == "EmptyLatentImage":
            for k in ("width", "height"):
                if k in node["inputs"]:
                    parameters[k] = node["inputs"][k]

    prompt_nodes = []
    negative_nodes = []
    for node in flow:
        if node["class_type"] == "CLIPTextEncode":
            is_negative = False
            for other in flow:
                if other["class_type"] in SAMPLER_NODE_TYPES:
                    neg_link = other["inputs"].get("negative")
                    if isinstance(neg_link, list) and neg_link[0] == node["node_id"]:
                        is_negative = True
                        break
            if is_negative:
                negative_nodes.append(node["node_id"])
            else:
                prompt_nodes.append(node["node_id"])

    has_load_image = any(ct in INPUT_NODE_TYPES - {"EmptyLatentImage"} for ct in class_types)
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


async def validate_workflow(
    workflow: dict[str, Any],
    client: ComfyUIClient,
    inspector: WorkflowInspector,
) -> dict[str, Any]:
    """Validate a workflow: structural checks, server checks, security inspection.

    Returns dict with: valid (bool), errors (list), warnings (list),
    node_count (int), pipeline (str).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Structural checks ---
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            errors.append(f"Node '{node_id}': not a valid node object")
            continue
        if "class_type" not in node_data:
            errors.append(f"Node '{node_id}': missing 'class_type'")
        inputs = node_data.get("inputs")
        if inputs is None:
            errors.append(f"Node '{node_id}': missing 'inputs'")
            continue
        if not isinstance(inputs, dict):
            errors.append(
                f"Node '{node_id}': 'inputs' must be an object, got {type(inputs).__name__}"
            )
            continue
        for input_name, value in inputs.items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                ref_id = value[0]
                if ref_id not in workflow:
                    errors.append(
                        f"Node '{node_id}' input '{input_name}':"
                        f" references non-existent node '{ref_id}'"
                    )

    # Cycle detection
    deps: dict[str, set[str]] = {}
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        deps.setdefault(node_id, set())
        inputs = node_data.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        for value in inputs.values():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and value[0] in workflow
            ):
                deps[node_id].add(value[0])
                deps.setdefault(value[0], set())

    sorter = graphlib.TopologicalSorter(deps)
    try:
        list(sorter.static_order())
    except graphlib.CycleError as e:
        errors.append(f"Workflow contains a cycle: {e}")

    # --- Server checks (best-effort, skip if structural errors already found) ---
    object_info: dict[str, Any] | None = None
    if not errors:
        with contextlib.suppress(httpx.HTTPError, OSError):
            object_info = await client.get_object_info()

    if errors:
        pass  # Skip server checks — structural errors already found
    elif object_info is None:
        warnings.append("ComfyUI server unreachable — server validation skipped")
    else:
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                continue
            ct = node_data.get("class_type", "")
            if ct and ct not in object_info:
                errors.append(f"Node '{node_id}': class_type '{ct}' not installed on server")

        # Check models exist — batch by folder, fetch in parallel
        folder_models: dict[str, list[tuple[str, str, str]]] = {}
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                continue
            ct = node_data.get("class_type", "")
            if ct in MODEL_LOADER_FIELDS:
                inputs = node_data.get("inputs")
                if not isinstance(inputs, dict):
                    continue
                for input_key, folder in MODEL_LOADER_FIELDS[ct]:
                    model_name = inputs.get(input_key, "")
                    if model_name:
                        folder_models.setdefault(folder, []).append((node_id, folder, model_name))

        async def _fetch_folder(folder: str) -> tuple[str, list[str]]:
            try:
                return folder, await client.get_models(folder)
            except (httpx.HTTPError, OSError):
                return folder, []

        folder_results = dict(await asyncio.gather(*[_fetch_folder(f) for f in folder_models]))

        for folder, checks in folder_models.items():
            available = folder_results.get(folder, [])
            for node_id, _folder, model_name in checks:
                if available and model_name not in available:
                    warnings.append(
                        f"Node '{node_id}': {folder} model '{model_name}' not found in '{folder}'"
                    )

    # --- Security inspection ---
    try:
        result = inspector.inspect(workflow)
        warnings.extend(result.warnings)
    except WorkflowBlockedError as e:
        errors.append(f"Security: {e}")
    except Exception as e:
        errors.append(f"Security inspection failed due to an internal error: {e}")

    # --- Analysis ---
    analysis = analyze_workflow(workflow, object_info)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": analysis["node_count"],
        "pipeline": analysis["pipeline"],
    }
