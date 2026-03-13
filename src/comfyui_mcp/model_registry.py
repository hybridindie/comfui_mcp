"""Canonical model loader registry.

Single source of truth for ComfyUI model loader node types, their input
fields, and the model folders they load from.  Both ``model_checker`` and
``workflow/validation`` derive their specialised views from this registry.
"""

from __future__ import annotations

# Maps node class_type -> list of (input field name, model folder) pairs.
# Most loaders have one model field, but some (DualCLIPLoader, TripleCLIPLoader)
# load multiple models from the same folder.
MODEL_LOADER_FIELDS: dict[str, list[tuple[str, str]]] = {
    "CheckpointLoaderSimple": [("ckpt_name", "checkpoints")],
    "CheckpointLoader": [("ckpt_name", "checkpoints")],
    "unCLIPCheckpointLoader": [("ckpt_name", "checkpoints")],
    "LoraLoader": [("lora_name", "loras")],
    "LoraLoaderModelOnly": [("lora_name", "loras")],
    "VAELoader": [("vae_name", "vae")],
    "ControlNetLoader": [("control_net_name", "controlnet")],
    "UpscaleModelLoader": [("model_name", "upscale_models")],
    "CLIPLoader": [("clip_name", "clip")],
    "CLIPVisionLoader": [("clip_name", "clip_vision")],
    "StyleModelLoader": [("style_model_name", "style_models")],
    "GLIGENLoader": [("gligen_name", "gligen")],
    "DiffusersLoader": [("model_path", "diffusers")],
    "UNETLoader": [("unet_name", "diffusion_models")],
    "DualCLIPLoader": [("clip_name1", "clip"), ("clip_name2", "clip")],
    "TripleCLIPLoader": [("clip_name1", "clip"), ("clip_name2", "clip"), ("clip_name3", "clip")],
    "PhotoMakerLoader": [("photomaker_model_name", "photomaker")],
    "IPAdapterModelLoader": [("ipadapter_file", "ipadapter")],
}


def get_single_field_loaders() -> dict[str, tuple[str, str]]:
    """Return loaders that have exactly one (field, folder) pair.

    Used by ``workflow/validation.py`` which only needs single-field loaders
    for workflow analysis (model extraction, summary display).
    """
    return {
        class_type: fields[0]
        for class_type, fields in MODEL_LOADER_FIELDS.items()
        if len(fields) == 1
    }
