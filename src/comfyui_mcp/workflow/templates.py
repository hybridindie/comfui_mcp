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


def _build_controlnet_template(
    preprocessor_class: str,
    preprocessor_inputs: dict[str, Any],
    control_net_name: str,
    filename_prefix: str,
) -> dict[str, dict[str, Any]]:
    """Build a ControlNet template graph with variant-specific preprocessing."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": "control.png"},
        },
        "3": {
            "class_type": preprocessor_class,
            "inputs": copy.deepcopy(preprocessor_inputs),
        },
        "4": {
            "class_type": "ControlNetLoader",
            "inputs": {"control_net_name": control_net_name},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["1", 1]},
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
        },
        "7": {
            "class_type": "ControlNetApplyAdvanced",
            "inputs": {
                "positive": ["5", 0],
                "negative": ["6", 0],
                "control_net": ["4", 0],
                "image": ["3", 0],
                "strength": 1.0,
                "start_percent": 0.0,
                "end_percent": 1.0,
            },
        },
        "8": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 512, "batch_size": 1},
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 0,
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["7", 1],
                "latent_image": ["8", 0],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["1", 2]},
        },
        "11": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["10", 0]},
        },
    }


# --- controlnet_canny template ---
_CONTROLNET_CANNY: dict[str, dict[str, Any]] = _build_controlnet_template(
    preprocessor_class="CannyEdgePreprocessor",
    preprocessor_inputs={
        "image": ["2", 0],
        "low_threshold": 100,
        "high_threshold": 200,
    },
    control_net_name="control_v11p_sd15_canny.safetensors",
    filename_prefix="comfyui-mcp-controlnet-canny",
)

# --- controlnet_depth template ---
_CONTROLNET_DEPTH: dict[str, dict[str, Any]] = _build_controlnet_template(
    preprocessor_class="MiDaS-DepthMapPreprocessor",
    preprocessor_inputs={
        "image": ["2", 0],
        "a": 2.0,
        "bg_threshold": 0.1,
    },
    control_net_name="control_v11f1p_sd15_depth.safetensors",
    filename_prefix="comfyui-mcp-controlnet-depth",
)

# --- controlnet_openpose template ---
_CONTROLNET_OPENPOSE: dict[str, dict[str, Any]] = _build_controlnet_template(
    preprocessor_class="DWPreprocessor",
    preprocessor_inputs={
        "image": ["2", 0],
        "resolution": 512,
    },
    control_net_name="control_v11p_sd15_openpose.safetensors",
    filename_prefix="comfyui-mcp-controlnet-openpose",
)

# --- ip_adapter template ---
_IP_ADAPTER: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
    },
    "2": {
        "class_type": "CLIPVisionLoader",
        "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"},
    },
    "3": {
        "class_type": "IPAdapterModelLoader",
        "inputs": {"ipadapter_file": "ip-adapter-plus_sdxl_vit-h.safetensors"},
    },
    "4": {
        "class_type": "LoadImage",
        "inputs": {"image": "reference.png"},
    },
    "5": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["1", 1]},
    },
    "7": {
        "class_type": "IPAdapterApply",
        "inputs": {
            "model": ["1", 0],
            "ipadapter": ["3", 0],
            "image": ["4", 0],
            "clip_vision": ["2", 0],
            "weight": 0.75,
        },
    },
    "8": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
    },
    "9": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 28,
            "cfg": 6.0,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 1.0,
            "model": ["7", 0],
            "positive": ["5", 0],
            "negative": ["6", 0],
            "latent_image": ["8", 0],
        },
    },
    "10": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["9", 0], "vae": ["1", 2]},
    },
    "11": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp-ipadapter", "images": ["10", 0]},
    },
}

# --- lora_stack template ---
_LORA_STACK: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "2": {
        "class_type": "LoraLoader",
        "inputs": {
            "model": ["1", 0],
            "clip": ["1", 1],
            "lora_name": "detail-tweaker.safetensors",
            "strength_model": 0.75,
            "strength_clip": 0.75,
        },
    },
    "3": {
        "class_type": "LoraLoader",
        "inputs": {
            "model": ["2", 0],
            "clip": ["2", 1],
            "lora_name": "style-cinematic.safetensors",
            "strength_model": 0.45,
            "strength_clip": 0.45,
        },
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["3", 1]},
    },
    "5": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "bad quality, blurry", "clip": ["3", 1]},
    },
    "6": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 768, "height": 768, "batch_size": 1},
    },
    "7": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 24,
            "cfg": 6.5,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 1.0,
            "model": ["3", 0],
            "positive": ["4", 0],
            "negative": ["5", 0],
            "latent_image": ["6", 0],
        },
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["7", 0], "vae": ["1", 2]},
    },
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp-lora-stack", "images": ["8", 0]},
    },
}

# --- face_restore template ---
_FACE_RESTORE: dict[str, dict[str, Any]] = {
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
        "class_type": "FaceRestoreModelLoader",
        "inputs": {"model_name": "codeformer.pth"},
    },
    "5": {
        "class_type": "FaceRestoreCFWithModel",
        "inputs": {"facerestore_model": ["4", 0], "image": ["3", 0], "fidelity": 0.7},
    },
    "6": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "comfyui-mcp-face-restore", "images": ["5", 0]},
    },
}

# --- flux_txt2img template ---
_FLUX_TXT2IMG: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "flux1-dev.safetensors"},
    },
    "2": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
    },
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["1", 1]},
    },
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "low quality, artifacts", "clip": ["1", 1]},
    },
    "5": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 1.0,
            "sampler_name": "euler",
            "scheduler": "simple",
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
        "inputs": {"filename_prefix": "comfyui-mcp-flux", "images": ["6", 0]},
    },
}

# --- sdxl_txt2img template ---
_SDXL_TXT2IMG: dict[str, dict[str, Any]] = {
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
    },
    "2": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
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
            "steps": 30,
            "cfg": 6.0,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
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
        "inputs": {"filename_prefix": "comfyui-mcp-sdxl", "images": ["6", 0]},
    },
}


# --- Param application ---

_PARAM_MAP: dict[str, list[tuple[str, str]]] = {
    "prompt": [("CLIPTextEncode", "text")],
    "negative_prompt": [],
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
    "controlnet_model": [("ControlNetLoader", "control_net_name")],
    "control_strength": [("ControlNetApplyAdvanced", "strength")],
    "ipadapter_model": [("IPAdapterModelLoader", "ipadapter_file")],
    "ipadapter_weight": [("IPAdapterApply", "weight")],
    "clip_vision_model": [("CLIPVisionLoader", "clip_name")],
    "lora_name": [("LoraLoader", "lora_name")],
    "lora_strength": [
        ("LoraLoader", "strength_model"),
        ("LoraLoader", "strength_clip"),
    ],
    "face_restore_model": [("FaceRestoreModelLoader", "model_name")],
    "face_restore_fidelity": [("FaceRestoreCFWithModel", "fidelity")],
}


def _apply_params(wf: dict[str, Any], params: dict[str, Any]) -> None:
    """Apply parameter overrides to a workflow in-place."""
    by_type: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for nid, ndata in wf.items():
        ct = ndata.get("class_type", "")
        by_type.setdefault(ct, []).append((nid, ndata))

    for param_name, value in params.items():
        if param_name == "negative_prompt":
            clip_nodes = by_type.get("CLIPTextEncode", [])
            if len(clip_nodes) >= 2:
                clip_nodes[1][1]["inputs"]["text"] = value
            continue

        if param_name == "prompt":
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
    "controlnet_canny": _CONTROLNET_CANNY,
    "controlnet_depth": _CONTROLNET_DEPTH,
    "controlnet_openpose": _CONTROLNET_OPENPOSE,
    "ip_adapter": _IP_ADAPTER,
    "lora_stack": _LORA_STACK,
    "face_restore": _FACE_RESTORE,
    "flux_txt2img": _FLUX_TXT2IMG,
    "sdxl_txt2img": _SDXL_TXT2IMG,
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
