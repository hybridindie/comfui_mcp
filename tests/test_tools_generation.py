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
from comfyui_mcp.tools.generation import (
    _format_summary,
    register_generation_tools,
)
from comfyui_mcp.workflow.validation import analyze_workflow as _analyze_workflow


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
        # Prompt/negative node detection
        assert result["prompt_nodes"] == ["6"]
        assert result["negative_nodes"] == ["7"]

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


class TestFormatSummary:
    def test_formats_txt2img_summary(self):
        analysis = {
            "node_count": 7,
            "class_types": [
                "CheckpointLoaderSimple",
                "EmptyLatentImage",
                "CLIPTextEncode",
                "CLIPTextEncode",
                "KSampler",
                "VAEDecode",
                "SaveImage",
            ],
            "flow": [
                {
                    "node_id": "4",
                    "class_type": "CheckpointLoaderSimple",
                    "display_name": "CheckpointLoaderSimple",
                    "inputs": {},
                },
                {
                    "node_id": "5",
                    "class_type": "EmptyLatentImage",
                    "display_name": "EmptyLatentImage",
                    "inputs": {"width": 512, "height": 512},
                },
                {
                    "node_id": "6",
                    "class_type": "CLIPTextEncode",
                    "display_name": "CLIPTextEncode",
                    "inputs": {},
                },
                {
                    "node_id": "7",
                    "class_type": "CLIPTextEncode",
                    "display_name": "CLIPTextEncode",
                    "inputs": {},
                },
                {
                    "node_id": "3",
                    "class_type": "KSampler",
                    "display_name": "KSampler",
                    "inputs": {"steps": 20, "cfg": 7.0},
                },
                {
                    "node_id": "8",
                    "class_type": "VAEDecode",
                    "display_name": "VAEDecode",
                    "inputs": {},
                },
                {
                    "node_id": "9",
                    "class_type": "SaveImage",
                    "display_name": "SaveImage",
                    "inputs": {},
                },
            ],
            "models": [{"name": "v1-5-pruned-emaonly.safetensors", "type": "checkpoint"}],
            "parameters": {
                "steps": 20,
                "cfg": 7.0,
                "sampler": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "width": 512,
                "height": 512,
            },
            "pipeline": "txt2img",
            "prompt_nodes": ["6"],
            "negative_nodes": ["7"],
        }
        result = _format_summary(analysis)
        assert "Workflow: 7 nodes" in result
        assert "Pipeline: txt2img" in result
        assert "v1-5-pruned-emaonly.safetensors (checkpoint)" in result
        assert "steps=20" in result
        assert "Prompt: node 6" in result
        assert "Negative: node 7" in result
        # Flow uses -> separator
        assert " -> " in result

    def test_formats_empty_workflow(self):
        analysis = {
            "node_count": 0,
            "class_types": [],
            "flow": [],
            "models": [],
            "parameters": {},
            "pipeline": "unknown",
            "prompt_nodes": [],
            "negative_nodes": [],
        }
        result = _format_summary(analysis)
        assert "Workflow: 0 nodes" in result

    def test_uses_display_names_in_flow(self):
        analysis = {
            "node_count": 1,
            "class_types": ["CheckpointLoaderSimple"],
            "flow": [
                {
                    "node_id": "1",
                    "class_type": "CheckpointLoaderSimple",
                    "display_name": "Load Checkpoint",
                    "inputs": {},
                },
            ],
            "models": [],
            "parameters": {},
            "pipeline": "unknown",
            "prompt_nodes": [],
            "negative_nodes": [],
        }
        result = _format_summary(analysis)
        assert "Load Checkpoint" in result

    def test_omits_prompt_line_when_no_prompt_nodes(self):
        analysis = {
            "node_count": 1,
            "class_types": ["SaveImage"],
            "flow": [
                {
                    "node_id": "1",
                    "class_type": "SaveImage",
                    "display_name": "SaveImage",
                    "inputs": {},
                }
            ],
            "models": [],
            "parameters": {},
            "pipeline": "unknown",
            "prompt_nodes": [],
            "negative_nodes": [],
        }
        result = _format_summary(analysis)
        assert "Prompt:" not in result
        assert "Negative:" not in result

    def test_omits_parameters_line_when_no_params(self):
        analysis = {
            "node_count": 1,
            "class_types": ["SaveImage"],
            "flow": [
                {
                    "node_id": "1",
                    "class_type": "SaveImage",
                    "display_name": "SaveImage",
                    "inputs": {},
                }
            ],
            "models": [],
            "parameters": {},
            "pipeline": "unknown",
            "prompt_nodes": [],
            "negative_nodes": [],
        }
        result = _format_summary(analysis)
        assert "Parameters:" not in result


class TestSummarizeWorkflow:
    @respx.mock
    async def test_summarizes_txt2img_workflow(self, components):
        client, audit, limiter, inspector = components
        read_limiter = RateLimiter(max_per_minute=60)
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "KSampler": {"display_name": "KSampler"},
                    "CheckpointLoaderSimple": {"display_name": "Load Checkpoint"},
                },
            )
        )
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            read_limiter=read_limiter,
        )
        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 512, "height": 512, "batch_size": 1},
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
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
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "a cat", "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "bad", "clip": ["4", 1]},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "test", "images": ["8", 0]},
            },
        }
        result = await tools["summarize_workflow"](workflow=json.dumps(workflow))
        assert "7 nodes" in result
        assert "txt2img" in result
        assert "model.safetensors" in result
        assert "Load Checkpoint" in result
        # Verify audit log was written
        audit_lines = audit._audit_file.read_text().strip().split("\n")
        audit_entries = [json.loads(line) for line in audit_lines]
        summary_entries = [e for e in audit_entries if e["tool"] == "summarize_workflow"]
        assert len(summary_entries) == 1
        assert summary_entries[0]["action"] == "summarized"

    @respx.mock
    async def test_fallback_when_object_info_fails(self, components):
        client, audit, limiter, inspector = components
        read_limiter = RateLimiter(max_per_minute=60)
        respx.get("http://test:8188/object_info").mock(side_effect=httpx.ConnectError("offline"))
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            read_limiter=read_limiter,
        )
        workflow = {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"},
            },
        }
        result = await tools["summarize_workflow"](workflow=json.dumps(workflow))
        assert "1 node" in result
        assert "CheckpointLoaderSimple" in result

    async def test_rejects_non_object_workflow(self, components):
        client, audit, limiter, inspector = components
        read_limiter = RateLimiter(max_per_minute=60)
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            read_limiter=read_limiter,
        )
        with pytest.raises(ValueError, match="JSON object"):
            await tools["summarize_workflow"](workflow="[1, 2, 3]")
        with pytest.raises(ValueError, match="JSON object"):
            await tools["summarize_workflow"](workflow='"just a string"')

    @respx.mock
    async def test_handles_non_dict_inputs(self, components):
        client, audit, limiter, inspector = components
        read_limiter = RateLimiter(max_per_minute=60)
        respx.get("http://test:8188/object_info").mock(return_value=httpx.Response(200, json={}))
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            read_limiter=read_limiter,
        )
        workflow = {
            "1": {
                "class_type": "KSampler",
                "inputs": [1, 2, 3],
            },
        }
        result = await tools["summarize_workflow"](workflow=json.dumps(workflow))
        assert "1 node" in result

    async def test_rejects_invalid_json(self, components):
        client, audit, limiter, inspector = components
        read_limiter = RateLimiter(max_per_minute=60)
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            read_limiter=read_limiter,
        )
        with pytest.raises(ValueError, match="Invalid JSON"):
            await tools["summarize_workflow"](workflow="not json")
