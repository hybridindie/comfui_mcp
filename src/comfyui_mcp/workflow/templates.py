"""Workflow templates for common ComfyUI pipelines."""

from __future__ import annotations

import copy
from typing import Any

# --- txt2img template ---
_TXT2IMG: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "2": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
    },
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["1", 0],
            "positive": ["3", 0],
            "negative": ["4", 0],
            "latent_image": ["2", 0],
        },
    },
    "6": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
    },
    "7": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp", "images": ["6", 0]},
    },
}

# --- img2img template ---
_IMG2IMG: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "2": {
        "class_type": "LoadImage",
        "inputs": {"image": "input.png"},
    },
    "3": {
        "class_type": "VAEEncode",
        "inputs": {"pixels": ["2", 0], "vae": ["1", 2]},
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "5": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
    },
    "6": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 0.75,
            "model": ["1", 0],
            "positive": ["4", 0],
            "negative": ["5", 0],
            "latent_image": ["3", 0],
        },
    },
    "7": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
    },
    "8": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp", "images": ["7", 0]},
    },
}

# --- upscale template ---
_UPSCALE: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "LoadImage",
        "inputs": {"image": "input.png"},
    },
    "2": {
        "class_type": "UpscaleModelLoader",
        "inputs": {"model_name": "RealESRGAN_x4plus.pth"},
    },
    "3": {
        "class_type": "ImageUpscaleWithModel",
        "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]},
    },
    "4": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp-upscale", "images": ["3", 0]},
    },
}

# --- inpaint template ---
_INPAINT: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "2": {
        "class_type": "LoadImage",
        "inputs": {"image": "input.png"},
    },
    "3": {
        "class_type": "LoadImageMask",
        "inputs": {"image": "mask.png", "channel": "alpha"},
    },
    "4": {
        "class_type": "VAEEncode",
        "inputs": {"pixels": ["2", 0], "vae": ["1", 2]},
    },
    "5": {
        "class_type": "SetLatentNoiseMask",
        "inputs": {"samples": ["4", 0], "mask": ["3", 0]},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
    },
    "8": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 0.8,
            "model": ["1", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "9": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["8", 0], "vae": ["1", 2]},
    },
    "10": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp-inpaint", "images": ["9", 0]},
    },
}

# --- txt2vid AnimateDiff template ---
_TXT2VID_ANIMATEDIFF: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "2": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 16},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
    },
    "5": {
        "class_type": "ADE_AnimateDiffLoaderWithContext",
        "inputs": {
            "model_name": "mm_sd_v15_v2.ckpt",
            "beta_schedule": "sqrt_linear (AnimateDiff)",
            "model": ["1", 0],
        },
    },
    "6": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7.0,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1.0,
            "model": ["5", 0],
            "positive": ["3", 0],
            "negative": ["4", 0],
            "latent_image": ["2", 0],
        },
    },
    "7": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
    },
    "8": {
        "class_type": "SaveAnimatedWEBP",
        "inputs": {
            "filename_prefix": "comfyui-mcp-anim",
            "fps": 8.0,
            "lossless": False,
            "quality": 85,
            "method": "default",
            "images": ["7", 0],
        },
    },
}

# --- txt2vid Wan template ---
_TXT2VID_WAN: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "DownloadAndLoadWanModel",
        "inputs": {
            "model": "Wan2.1-T2V-14B-bf16",
        },
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
    },
    "4": {
        "class_type": "WanTextToVideo",
        "inputs": {
            "width": 832,
            "height": 480,
            "num_frames": 81,
            "steps": 30,
            "cfg": 5.0,
            "seed": 0,
            "model": ["1", 0],
            "positive": ["2", 0],
            "negative": ["3", 0],
        },
    },
    "5": {
        "class_type": "SaveAnimatedWEBP",
        "inputs": {
            "filename_prefix": "comfyui-mcp-wan",
            "fps": 16.0,
            "lossless": False,
            "quality": 85,
            "method": "default",
            "images": ["4", 0],
        },
    },
}


# --- Param application ---

# Maps param name -> list of (class_type, input_key) targets
_PARAM_MAP: dict[str, list[tuple[str, str]]] = {
    "prompt": [("CLIPTextEncode", "text")],  # Applied only to the first (positive) CLIPTextEncode
    "negative_prompt": [],  # Special handling: applied to second CLIPTextEncode
    "width": [("EmptyLatentImage", "width"), ("WanTextToVideo", "width")],
    "height": [("EmptyLatentImage", "height"), ("WanTextToVideo", "height")],
    "steps": [("KSampler", "steps"), ("WanTextToVideo", "steps")],
    "cfg": [("KSampler", "cfg"), ("WanTextToVideo", "cfg")],
    "denoise": [("KSampler", "denoise")],
    "model": [("CheckpointLoaderSimple", "ckpt_name")],
    "model_name": [("UpscaleModelLoader", "model_name")],
    "motion_module": [("ADE_AnimateDiffLoaderWithContext", "model_name")],
    "frames": [("EmptyLatentImage", "batch_size"), ("WanTextToVideo", "num_frames")],
    "seed": [("KSampler", "seed"), ("WanTextToVideo", "seed")],
    "sampler_name": [("KSampler", "sampler_name")],
    "scheduler": [("KSampler", "scheduler")],
    "image": [("LoadImage", "image")],
    "mask": [("LoadImageMask", "image")],
    "fps": [("SaveAnimatedWEBP", "fps")],
}


def _apply_params(wf: dict[str, Any], params: dict[str, Any]) -> None:
    """Apply parameter overrides to a workflow in-place."""
    # Build a lookup: class_type -> list of (node_id, node_data)
    by_type: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for nid, ndata in wf.items():
        ct = ndata.get("class_type", "")
        by_type.setdefault(ct, []).append((nid, ndata))

    for param_name, value in params.items():
        if param_name == "negative_prompt":
            # Apply to the second CLIPTextEncode (negative)
            clip_nodes = by_type.get("CLIPTextEncode", [])
            if len(clip_nodes) >= 2:
                clip_nodes[1][1]["inputs"]["text"] = value
            continue

        if param_name == "prompt":
            # Apply to the first CLIPTextEncode (positive)
            clip_nodes = by_type.get("CLIPTextEncode", [])
            if clip_nodes:
                clip_nodes[0][1]["inputs"]["text"] = value
            continue

        targets = _PARAM_MAP.get(param_name, [])
        for class_type, input_key in targets:
            for _, ndata in by_type.get(class_type, []):
                if input_key in ndata["inputs"]:
                    ndata["inputs"][input_key] = value


TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "txt2img": _TXT2IMG,
    "img2img": _IMG2IMG,
    "upscale": _UPSCALE,
    "inpaint": _INPAINT,
    "txt2vid_animatediff": _TXT2VID_ANIMATEDIFF,
    "txt2vid_wan": _TXT2VID_WAN,
}


def create_from_template(template: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a workflow from a named template with optional param overrides."""
    if template not in TEMPLATES:
        raise ValueError(
            f"Unknown template '{template}'. Available: {', '.join(sorted(TEMPLATES))}"
        )
    wf = copy.deepcopy(TEMPLATES[template])
    if params:
        _apply_params(wf, params)
    return wf
