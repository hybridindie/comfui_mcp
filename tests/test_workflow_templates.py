"""Tests for workflow templates."""

from __future__ import annotations

from typing import Any

import pytest

from comfyui_mcp.workflow.templates import TEMPLATES, create_from_template


def _get_nodes_by_type(wf: dict[str, Any], class_type: str) -> list[dict[str, Any]]:
    """Find all nodes of a given class_type in a workflow."""
    return [v for v in wf.values() if v.get("class_type") == class_type]


def _has_connection_to(wf: dict[str, Any], target_node_id: str, input_name: str) -> bool:
    """Check if a node's input is a connection (list reference)."""
    node = wf.get(target_node_id)
    if not node:
        return False
    value = node.get("inputs", {}).get(input_name)
    return isinstance(value, list) and len(value) == 2


class TestTxt2ImgTemplate:
    def test_returns_valid_workflow(self):
        wf = create_from_template("txt2img")
        assert isinstance(wf, dict)
        assert len(wf) >= 7
        class_types = {v["class_type"] for v in wf.values()}
        assert "CheckpointLoaderSimple" in class_types
        assert "EmptyLatentImage" in class_types
        assert "KSampler" in class_types
        assert "CLIPTextEncode" in class_types
        assert "VAEDecode" in class_types
        assert "SaveImage" in class_types

    def test_params_override_defaults(self):
        wf = create_from_template(
            "txt2img", {"prompt": "a dog", "width": 768, "height": 1024, "steps": 30}
        )
        latent_nodes = _get_nodes_by_type(wf, "EmptyLatentImage")
        assert latent_nodes[0]["inputs"]["width"] == 768
        assert latent_nodes[0]["inputs"]["height"] == 1024
        sampler_nodes = _get_nodes_by_type(wf, "KSampler")
        assert sampler_nodes[0]["inputs"]["steps"] == 30
        clip_nodes = _get_nodes_by_type(wf, "CLIPTextEncode")
        texts = [n["inputs"].get("text") for n in clip_nodes]
        assert "a dog" in texts

    def test_model_override(self):
        wf = create_from_template("txt2img", {"model": "dreamshaper_v8.safetensors"})
        loader = _get_nodes_by_type(wf, "CheckpointLoaderSimple")
        assert loader[0]["inputs"]["ckpt_name"] == "dreamshaper_v8.safetensors"

    def test_unknown_params_ignored(self):
        wf = create_from_template("txt2img", {"nonexistent_param": 999})
        assert isinstance(wf, dict)


class TestImg2ImgTemplate:
    def test_returns_valid_workflow(self):
        wf = create_from_template("img2img")
        class_types = {v["class_type"] for v in wf.values()}
        assert "CheckpointLoaderSimple" in class_types
        assert "LoadImage" in class_types
        assert "KSampler" in class_types
        assert "VAEEncode" in class_types
        assert "VAEDecode" in class_types
        assert "SaveImage" in class_types

    def test_denoise_param(self):
        wf = create_from_template("img2img", {"denoise": 0.6})
        sampler = _get_nodes_by_type(wf, "KSampler")
        assert sampler[0]["inputs"]["denoise"] == 0.6


class TestUpscaleTemplate:
    def test_returns_valid_workflow(self):
        wf = create_from_template("upscale")
        class_types = {v["class_type"] for v in wf.values()}
        assert "LoadImage" in class_types
        assert "UpscaleModelLoader" in class_types
        assert "ImageUpscaleWithModel" in class_types
        assert "SaveImage" in class_types

    def test_model_name_override(self):
        wf = create_from_template("upscale", {"model_name": "4x_NMKD-Superscale-SP_178000_G.pth"})
        loader = _get_nodes_by_type(wf, "UpscaleModelLoader")
        assert loader[0]["inputs"]["model_name"] == "4x_NMKD-Superscale-SP_178000_G.pth"


class TestInpaintTemplate:
    def test_returns_valid_workflow(self):
        wf = create_from_template("inpaint")
        class_types = {v["class_type"] for v in wf.values()}
        assert "LoadImage" in class_types
        assert "LoadImageMask" in class_types
        assert "SetLatentNoiseMask" in class_types
        assert "KSampler" in class_types
        assert "VAEDecode" in class_types


class TestTxt2VidAnimateDiffTemplate:
    def test_returns_valid_workflow(self):
        wf = create_from_template("txt2vid_animatediff")
        class_types = {v["class_type"] for v in wf.values()}
        assert "ADE_AnimateDiffLoaderWithContext" in class_types
        assert "KSampler" in class_types
        assert "SaveAnimatedWEBP" in class_types

    def test_frames_param(self):
        wf = create_from_template("txt2vid_animatediff", {"frames": 32})
        latent = _get_nodes_by_type(wf, "EmptyLatentImage")
        assert latent[0]["inputs"]["batch_size"] == 32

    def test_motion_module_param(self):
        wf = create_from_template("txt2vid_animatediff", {"motion_module": "mm_sd15_v3.ckpt"})
        ad = _get_nodes_by_type(wf, "ADE_AnimateDiffLoaderWithContext")
        assert ad[0]["inputs"]["model_name"] == "mm_sd15_v3.ckpt"


class TestTxt2VidWanTemplate:
    def test_returns_valid_workflow(self):
        wf = create_from_template("txt2vid_wan")
        class_types = {v["class_type"] for v in wf.values()}
        assert "DownloadAndLoadWanModel" in class_types
        assert "WanTextToVideo" in class_types
        assert "SaveAnimatedWEBP" in class_types

    def test_dimensions_param(self):
        wf = create_from_template("txt2vid_wan", {"width": 1280, "height": 720})
        wan = _get_nodes_by_type(wf, "WanTextToVideo")
        assert wan[0]["inputs"]["width"] == 1280
        assert wan[0]["inputs"]["height"] == 720

    def test_frames_param(self):
        wf = create_from_template("txt2vid_wan", {"frames": 49})
        wan = _get_nodes_by_type(wf, "WanTextToVideo")
        assert wan[0]["inputs"]["num_frames"] == 49


class TestInvalidTemplate:
    def test_invalid_template_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            create_from_template("nonexistent")

    def test_templates_registry_has_all(self):
        expected = {
            "txt2img",
            "img2img",
            "upscale",
            "inpaint",
            "txt2vid_animatediff",
            "txt2vid_wan",
            "controlnet_canny",
            "controlnet_depth",
            "controlnet_openpose",
            "ip_adapter",
            "lora_stack",
            "face_restore",
            "flux_txt2img",
            "sdxl_txt2img",
        }
        assert set(TEMPLATES.keys()) == expected


class TestExpandedTemplates:
    def test_controlnet_canny_has_expected_nodes(self):
        wf = create_from_template("controlnet_canny")
        class_types = {v["class_type"] for v in wf.values()}
        assert "CannyEdgePreprocessor" in class_types
        assert "ControlNetLoader" in class_types
        assert "ControlNetApplyAdvanced" in class_types

    def test_controlnet_depth_override(self):
        wf = create_from_template(
            "controlnet_depth",
            {"controlnet_model": "custom-depth.safetensors", "control_strength": 0.65},
        )
        loader = _get_nodes_by_type(wf, "ControlNetLoader")
        assert loader[0]["inputs"]["control_net_name"] == "custom-depth.safetensors"
        apply = _get_nodes_by_type(wf, "ControlNetApplyAdvanced")
        assert apply[0]["inputs"]["strength"] == 0.65

    def test_ip_adapter_weight_override(self):
        wf = create_from_template(
            "ip_adapter",
            {
                "ipadapter_model": "ip-adapter_sdxl.safetensors",
                "clip_vision_model": "clip-vit-bigg-14.safetensors",
                "ipadapter_weight": 0.5,
            },
        )
        ip_model = _get_nodes_by_type(wf, "IPAdapterModelLoader")
        assert ip_model[0]["inputs"]["ipadapter_file"] == "ip-adapter_sdxl.safetensors"
        clip_vision = _get_nodes_by_type(wf, "CLIPVisionLoader")
        assert clip_vision[0]["inputs"]["clip_name"] == "clip-vit-bigg-14.safetensors"
        apply = _get_nodes_by_type(wf, "IPAdapterApply")
        assert apply[0]["inputs"]["weight"] == 0.5

    def test_lora_stack_overrides(self):
        wf = create_from_template(
            "lora_stack",
            {"lora_name": "my_style.safetensors", "lora_strength": 0.9},
        )
        loras = _get_nodes_by_type(wf, "LoraLoader")
        assert loras
        for lora in loras:
            assert lora["inputs"]["lora_name"] == "my_style.safetensors"
            assert lora["inputs"]["strength_model"] == 0.9
            assert lora["inputs"]["strength_clip"] == 0.9

    def test_face_restore_and_family_specific_templates(self):
        face_wf = create_from_template(
            "face_restore",
            {"model_name": "4x-UltraSharp.pth", "face_restore_model": "gfpgan_v1.4.pth"},
        )
        upscaler = _get_nodes_by_type(face_wf, "UpscaleModelLoader")
        assert upscaler[0]["inputs"]["model_name"] == "4x-UltraSharp.pth"
        restore = _get_nodes_by_type(face_wf, "FaceRestoreModelLoader")
        assert restore[0]["inputs"]["model_name"] == "gfpgan_v1.4.pth"

        flux_wf = create_from_template("flux_txt2img")
        flux_sampler = _get_nodes_by_type(flux_wf, "KSampler")
        assert flux_sampler[0]["inputs"]["cfg"] == 1.0

        sdxl_wf = create_from_template("sdxl_txt2img")
        sdxl_sampler = _get_nodes_by_type(sdxl_wf, "KSampler")
        assert sdxl_sampler[0]["inputs"]["scheduler"] == "karras"
