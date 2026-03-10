"""Tests for generation and workflow execution MCP tools."""

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowBlockedError, WorkflowInspector
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.tools.generation import _analyze_workflow, register_generation_tools


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    inspector = WorkflowInspector(
        mode="audit",
        dangerous_nodes=["EvalNode"],
        allowed_nodes=[],
    )
    return client, audit, limiter, inspector


@pytest.fixture
def enforce_components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    inspector = WorkflowInspector(
        mode="enforce",
        dangerous_nodes=["EvalNode"],
        allowed_nodes=[
            "KSampler",
            "CLIPTextEncode",
            "VAEDecode",
            "SaveImage",
            "CheckpointLoaderSimple",
            "EmptyLatentImage",
        ],
    )
    return client, audit, limiter, inspector


class TestRunWorkflow:
    @respx.mock
    async def test_submits_workflow(self, components):
        client, audit, limiter, inspector = components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
        result = await tools["run_workflow"](workflow=json.dumps(workflow))
        assert "abc-123" in result

    @respx.mock
    async def test_audit_mode_logs_dangerous_nodes(self, components):
        client, audit, limiter, inspector = components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = {"1": {"class_type": "EvalNode", "inputs": {}}}
        result = await tools["run_workflow"](workflow=json.dumps(workflow))
        assert "abc-123" in result
        assert "EvalNode" in result

    async def test_enforce_mode_blocks_unapproved(self, enforce_components):
        client, audit, limiter, inspector = enforce_components
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = {"1": {"class_type": "MaliciousNode", "inputs": {}}}
        with pytest.raises(WorkflowBlockedError):
            await tools["run_workflow"](workflow=json.dumps(workflow))


class TestGenerateImage:
    @respx.mock
    async def test_generate_image_submits_default_workflow(self, components):
        client, audit, limiter, inspector = components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "img-001"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        result = await tools["generate_image"](prompt="a beautiful sunset over mountains")
        assert "img-001" in result

    async def test_rejects_invalid_width(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="width"):
            await tools["generate_image"](prompt="test", width=10)

    async def test_rejects_invalid_height(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="height"):
            await tools["generate_image"](prompt="test", height=5000)

    async def test_rejects_invalid_steps(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="steps"):
            await tools["generate_image"](prompt="test", steps=0)

    async def test_rejects_invalid_cfg(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="cfg"):
            await tools["generate_image"](prompt="test", cfg=0.5)


class TestAnalyzeWorkflow:
    def test_analyzes_default_txt2img(self):
        workflow = {
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
                "inputs": {"text": "a cat", "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "bad quality", "clip": ["4", 1]},
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
        result = _analyze_workflow(workflow, object_info=None)

        assert result["node_count"] == 7
        assert "CheckpointLoaderSimple" in result["class_types"]
        assert {"name": "v1-5-pruned-emaonly.safetensors", "type": "checkpoint"} in result["models"]
        assert result["parameters"]["steps"] == 20
        assert result["parameters"]["cfg"] == 7.0
        assert result["parameters"]["sampler"] == "euler"
        assert result["parameters"]["width"] == 512
        assert result["parameters"]["height"] == 512
        # Flow should be topologically sorted
        flow = [n["class_type"] for n in result["flow"]]
        assert flow.index("CheckpointLoaderSimple") < flow.index("KSampler")
        assert flow.index("KSampler") < flow.index("VAEDecode")
        assert flow.index("VAEDecode") < flow.index("SaveImage")

    def test_extracts_multiple_models(self):
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "dreamshaper_v8.safetensors"},
            },
            "2": {
                "class_type": "LoraLoader",
                "inputs": {
                    "lora_name": "add-detail.safetensors",
                    "model": ["1", 0],
                    "clip": ["1", 1],
                },
            },
        }
        result = _analyze_workflow(workflow, object_info=None)
        names = [m["name"] for m in result["models"]]
        assert "dreamshaper_v8.safetensors" in names
        assert "add-detail.safetensors" in names

    def test_uses_display_names_from_object_info(self):
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"},
            },
        }
        object_info = {
            "CheckpointLoaderSimple": {
                "display_name": "Load Checkpoint",
            },
        }
        result = _analyze_workflow(workflow, object_info=object_info)
        assert result["flow"][0]["display_name"] == "Load Checkpoint"

    def test_handles_empty_workflow(self):
        result = _analyze_workflow({}, object_info=None)
        assert result["node_count"] == 0
        assert result["flow"] == []
        assert result["models"] == []

    def test_detects_pipeline_type_txt2img(self):
        workflow = {
            "1": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 512, "height": 512},
            },
            "2": {"class_type": "KSampler", "inputs": {"latent_image": ["1", 0]}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        }
        result = _analyze_workflow(workflow, object_info=None)
        assert result["pipeline"] == "txt2img"

    def test_detects_pipeline_type_img2img(self):
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
            "2": {"class_type": "KSampler", "inputs": {"latent_image": ["1", 0]}},
            "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        }
        result = _analyze_workflow(workflow, object_info=None)
        assert result["pipeline"] == "img2img"
