"""Workflow validation: structural checks, server checks, and security inspection."""

from __future__ import annotations

import graphlib
from typing import Any, TypedDict

# Node class_types that load models, mapped to their model input key and type label
MODEL_LOADERS: dict[str, tuple[str, str]] = {
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
        if ct in MODEL_LOADERS:
            key, model_type = MODEL_LOADERS[ct]
            name = node["inputs"].get(key, "")
            if name:
                models.append({"name": name, "type": model_type})

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
