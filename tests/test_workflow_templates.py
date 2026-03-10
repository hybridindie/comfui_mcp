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
        }
        assert set(TEMPLATES.keys()) == expected
