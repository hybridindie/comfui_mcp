"""Tests for generation and workflow execution MCP tools."""

import json
import unittest.mock

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.progress import WebSocketProgress
from comfyui_mcp.security.inspector import WorkflowBlockedError, WorkflowInspector
from comfyui_mcp.security.model_checker import ModelChecker
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathValidationError
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


@pytest.fixture
def progress_components(tmp_path, monkeypatch):
    """Components with progress tracking enabled."""
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    inspector = WorkflowInspector(
        mode="audit",
        dangerous_nodes=["EvalNode"],
        allowed_nodes=[],
    )
    progress = WebSocketProgress(client, timeout=10.0)
    return client, audit, limiter, inspector, progress, monkeypatch


class TestRunWorkflow:
    @respx.mock
    async def test_submits_workflow(self, components):
        client, audit, limiter, inspector = components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
        result = await tools["run_workflow"](workflow=json.dumps(workflow))
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result

    @respx.mock
    async def test_audit_mode_logs_dangerous_nodes(self, components):
        client, audit, limiter, inspector = components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = {"1": {"class_type": "EvalNode", "inputs": {}}}
        result = await tools["run_workflow"](workflow=json.dumps(workflow))
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result
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
        assert {"name": "v1-5-pruned-emaonly.safetensors", "type": "checkpoints"} in result[
            "models"
        ]
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
            "models": [{"name": "v1-5-pruned-emaonly.safetensors", "type": "checkpoints"}],
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
        assert "v1-5-pruned-emaonly.safetensors (checkpoints)" in result
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

    @respx.mock
    async def test_mermaid_escapes_html_characters(self, components):
        """Mermaid labels must HTML-escape <, >, &, and " from workflow values."""
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
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": '<script>alert("xss")</script>&model.safetensors'},
            },
        }
        result = await tools["summarize_workflow"](
            workflow=json.dumps(workflow),
            format="mermaid",
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "&amp;" in result
        assert "&#34;" in result

    @respx.mock
    async def test_supports_mermaid_output(self, components):
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
                    "model": ["4", 0],
                    "latent_image": ["5", 0],
                },
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

        result = await tools["summarize_workflow"](
            workflow=json.dumps(workflow),
            format="mermaid",
        )

        assert "flowchart LR" in result
        assert "-->|MODEL|" in result
        assert "-->|LATENT|" in result
        assert "classDef loader" in result
        assert "classDef sampler" in result
        assert "classDef output" in result

    async def test_rejects_invalid_format(self, components):
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

        with pytest.raises(ValueError, match='format must be either "text" or "mermaid"'):
            await tools["summarize_workflow"](workflow="{}", format="yaml")


class TestGenerateImageWait:
    @respx.mock
    async def test_wait_true_returns_structured_result(self, progress_components):
        client, audit, limiter, inspector, progress, monkeypatch = progress_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "img-wait-1"})
        )

        from comfyui_mcp.progress import ProgressState

        async def fake_wait(prompt_id):
            return ProgressState(
                prompt_id=prompt_id,
                status="completed",
                elapsed_seconds=12.3,
                outputs=[{"node_id": "9", "filename": "cat.png", "subfolder": "output"}],
            )

        monkeypatch.setattr(progress, "wait_for_completion", fake_wait)

        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            progress=progress,
        )
        result = await tools["generate_image"](prompt="a cat", wait=True)
        data = json.loads(result)
        assert data["prompt_id"] == "img-wait-1"
        assert data["status"] == "completed"
        assert len(data["outputs"]) == 1

    @respx.mock
    async def test_wait_false_returns_prompt_id_string(self, progress_components):
        client, audit, limiter, inspector, progress, _ = progress_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "img-nowait"})
        )
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            progress=progress,
        )
        result = await tools["generate_image"](prompt="a dog", wait=False)
        assert "img-nowait" in result
        assert not result.startswith("{")


class TestRunWorkflowWait:
    @respx.mock
    async def test_wait_true_returns_structured_result(self, progress_components):
        client, audit, limiter, inspector, progress, monkeypatch = progress_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "wait-123"})
        )

        from comfyui_mcp.progress import ProgressState

        async def fake_wait(prompt_id):
            return ProgressState(
                prompt_id=prompt_id,
                status="completed",
                elapsed_seconds=5.2,
                outputs=[{"node_id": "9", "filename": "out.png", "subfolder": "output"}],
            )

        monkeypatch.setattr(progress, "wait_for_completion", fake_wait)

        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            progress=progress,
        )
        result = await tools["run_workflow"](
            workflow=json.dumps({"1": {"class_type": "KSampler", "inputs": {}}}),
            wait=True,
        )
        data = json.loads(result)
        assert data["prompt_id"] == "wait-123"
        assert data["status"] == "completed"
        assert data["elapsed_seconds"] == 5.2
        assert len(data["outputs"]) == 1

    @respx.mock
    async def test_wait_false_returns_prompt_id_string(self, progress_components):
        client, audit, limiter, inspector, progress, _ = progress_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "nowait-456"})
        )
        mcp_server = FastMCP("test")
        tools = register_generation_tools(
            mcp_server,
            client,
            audit,
            limiter,
            inspector,
            progress=progress,
        )
        result = await tools["run_workflow"](
            workflow=json.dumps({"1": {"class_type": "KSampler", "inputs": {}}}),
            wait=False,
        )
        assert "nowait-456" in result
        # Should be plain string, not JSON
        assert not result.startswith("{")


class TestModelCheckIntegration:
    @respx.mock
    async def test_run_workflow_warns_missing_model(self, components):
        client, audit, limiter, inspector = components
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["other_model.safetensors"])
        )
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )
        )
        mcp_server = FastMCP("test")
        model_checker = ModelChecker()
        tools = register_generation_tools(
            mcp_server, client, audit, limiter, inspector, model_checker=model_checker
        )
        workflow = json.dumps(
            {
                "4": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "missing_model.safetensors"},
                },
                "3": {
                    "class_type": "KSampler",
                    "inputs": {"model": ["4", 0]},
                },
            }
        )
        result = await tools["run_workflow"](workflow=workflow)
        assert "Missing model" in result
        assert "missing_model.safetensors" in result
        assert "search_models" in result

    @respx.mock
    async def test_run_workflow_no_warning_when_model_present(self, components):
        client, audit, limiter, inspector = components
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["present_model.safetensors"])
        )
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-456"})
        )
        mcp_server = FastMCP("test")
        model_checker = ModelChecker()
        tools = register_generation_tools(
            mcp_server, client, audit, limiter, inspector, model_checker=model_checker
        )
        workflow = json.dumps(
            {
                "4": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "present_model.safetensors"},
                },
            }
        )
        result = await tools["run_workflow"](workflow=workflow)
        assert "abc-456" in result
        assert "Missing model" not in result

    @respx.mock
    async def test_generate_image_warns_missing_model(self, components):
        client, audit, limiter, inspector = components
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["other_model.safetensors"])
        )
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "img-001"})
        )
        mcp_server = FastMCP("test")
        model_checker = ModelChecker()
        tools = register_generation_tools(
            mcp_server, client, audit, limiter, inspector, model_checker=model_checker
        )
        result = await tools["generate_image"](prompt="a cat", model="missing_model.safetensors")
        assert "Missing model" in result
        assert "missing_model.safetensors" in result

    async def test_run_workflow_enforce_mode_blocks_missing_model(self, tmp_path):
        client = ComfyUIClient(base_url="http://test:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(
            mode="enforce",
            dangerous_nodes=[],
            allowed_nodes=["CheckpointLoaderSimple", "KSampler"],
        )
        mcp_server = FastMCP("test")
        model_checker = ModelChecker()

        _missing_warning = (
            "Missing model: 'gone.safetensors' not found in checkpoints. "
            "Use search_models to find and download_model to install it."
        )

        async def fake_check_models(wf, cl):
            return [_missing_warning]

        with unittest.mock.patch.object(
            model_checker, "check_models", side_effect=fake_check_models
        ):
            tools = register_generation_tools(
                mcp_server, client, audit, limiter, inspector, model_checker=model_checker
            )
            workflow = json.dumps(
                {
                    "4": {
                        "class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "gone.safetensors"},
                    },
                }
            )
            with pytest.raises(WorkflowBlockedError, match="missing models"):
                await tools["run_workflow"](workflow=workflow)

    @respx.mock
    async def test_run_workflow_no_model_checker_passes_through(self, components):
        client, audit, limiter, inspector = components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "pass-123"})
        )
        mcp_server = FastMCP("test")
        # No model_checker passed — should work fine without checking models
        tools = register_generation_tools(mcp_server, client, audit, limiter, inspector)
        workflow = json.dumps(
            {
                "4": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "any_model.safetensors"},
                },
            }
        )
        result = await tools["run_workflow"](workflow=workflow)
        assert "pass-123" in result
        assert "Missing model" not in result


class TestConvenienceTools:
    """Tests for transform_image, inpaint_image, and upscale_image."""

    @pytest.fixture
    def gen_components(self, tmp_path):
        from comfyui_mcp.security.sanitizer import PathSanitizer

        client = ComfyUIClient(base_url="http://test:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(mode="audit", dangerous_nodes=[], allowed_nodes=[])
        sanitizer = PathSanitizer(allowed_extensions=[".png", ".jpg", ".webp", ".pth"])
        return client, audit, limiter, inspector, sanitizer

    # --- transform_image ---

    @respx.mock
    async def test_transform_image_submits_workflow(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "t2i-001"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        result = await tools["transform_image"](image="input.png", prompt="a cat in a hat")
        assert "t2i-001" in result

    @respx.mock
    async def test_transform_image_puts_prompt_in_workflow(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        captured: dict = {}

        async def capture(data, **_kwargs):
            captured["workflow"] = data
            return {"prompt_id": "cap-001"}

        import unittest.mock

        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with unittest.mock.patch.object(client, "post_prompt", side_effect=capture):
            await tools["transform_image"](
                image="input.png", prompt="my custom prompt", strength=0.5
            )

        wf = captured["workflow"]
        clip_nodes = [n for n in wf.values() if n["class_type"] == "CLIPTextEncode"]
        prompts = [n["inputs"]["text"] for n in clip_nodes]
        assert "my custom prompt" in prompts
        ksampler = next(n for n in wf.values() if n["class_type"] == "KSampler")
        assert ksampler["inputs"]["denoise"] == 0.5

    async def test_transform_image_rejects_invalid_strength(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with pytest.raises(ValueError, match="strength"):
            await tools["transform_image"](image="x.png", prompt="p", strength=1.5)

    async def test_transform_image_rejects_path_traversal(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with pytest.raises(PathValidationError, match="traversal"):
            await tools["transform_image"](image="../evil.png", prompt="p")

    @respx.mock
    async def test_transform_image_audit_log_written(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "audit-t"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        await tools["transform_image"](image="ref.png", prompt="a landscape")
        lines = audit._audit_file.read_text().strip().split("\n")
        entries = [json.loads(line) for line in lines]
        assert any(e["tool"] == "transform_image" and e["action"] == "submitted" for e in entries)

    # --- inpaint_image ---

    @respx.mock
    async def test_inpaint_image_submits_workflow(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "inp-001"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        result = await tools["inpaint_image"](
            image="scene.png", mask="mask.png", prompt="a blue sky"
        )
        assert "inp-001" in result

    @respx.mock
    async def test_inpaint_image_uses_both_filenames(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        captured: dict = {}

        async def capture(data, **_kwargs):
            captured["workflow"] = data
            return {"prompt_id": "cap-002"}

        import unittest.mock

        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with unittest.mock.patch.object(client, "post_prompt", side_effect=capture):
            await tools["inpaint_image"](image="scene.png", mask="mask.png", prompt="a tree")

        wf = captured["workflow"]
        load_image = next(n for n in wf.values() if n["class_type"] == "LoadImage")
        load_mask = next(n for n in wf.values() if n["class_type"] == "LoadImageMask")
        assert load_image["inputs"]["image"] == "scene.png"
        assert load_mask["inputs"]["image"] == "mask.png"

    async def test_inpaint_image_rejects_mask_traversal(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with pytest.raises(PathValidationError, match="traversal"):
            await tools["inpaint_image"](image="ok.png", mask="../../etc/passwd", prompt="p")

    async def test_inpaint_image_rejects_invalid_steps(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with pytest.raises(ValueError, match="steps"):
            await tools["inpaint_image"](image="x.png", mask="m.png", prompt="p", steps=0)

    # --- upscale_image ---

    @respx.mock
    async def test_upscale_image_submits_workflow(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "up-001"})
        )
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        result = await tools["upscale_image"](image="small.png")
        assert "up-001" in result

    @respx.mock
    async def test_upscale_image_uses_custom_model(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        captured: dict = {}

        async def capture(data, **_kwargs):
            captured["workflow"] = data
            return {"prompt_id": "cap-003"}

        import unittest.mock

        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with unittest.mock.patch.object(client, "post_prompt", side_effect=capture):
            await tools["upscale_image"](image="photo.png", upscale_model="4x-UltraSharp.pth")

        wf = captured["workflow"]
        loader = next(n for n in wf.values() if n["class_type"] == "UpscaleModelLoader")
        assert loader["inputs"]["model_name"] == "4x-UltraSharp.pth"

    async def test_upscale_image_rejects_path_traversal(self, gen_components):
        client, audit, limiter, inspector, sanitizer = gen_components
        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer
        )
        with pytest.raises(PathValidationError, match="traversal"):
            await tools["upscale_image"](image="../../secret.png")

    @respx.mock
    async def test_upscale_image_wait_returns_structured_result(self, tmp_path):
        from comfyui_mcp.progress import ProgressState
        from comfyui_mcp.security.sanitizer import PathSanitizer

        client = ComfyUIClient(base_url="http://test:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(mode="audit", dangerous_nodes=[], allowed_nodes=[])
        sanitizer = PathSanitizer(allowed_extensions=[".png", ".jpg", ".pth"])
        progress = WebSocketProgress(client, timeout=10.0)

        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "up-wait-1"})
        )

        async def fake_wait(prompt_id):
            return ProgressState(
                prompt_id=prompt_id,
                status="completed",
                elapsed_seconds=3.0,
                outputs=[{"node_id": "4", "filename": "upscaled.png", "subfolder": "output"}],
            )

        import unittest.mock

        mcp = FastMCP("test")
        tools = register_generation_tools(
            mcp, client, audit, limiter, inspector, sanitizer=sanitizer, progress=progress
        )
        with unittest.mock.patch.object(progress, "wait_for_completion", side_effect=fake_wait):
            result = await tools["upscale_image"](image="small.png", wait=True)

        data = json.loads(result)
        assert data["prompt_id"] == "up-wait-1"
        assert data["status"] == "completed"
        assert len(data["outputs"]) == 1

    # --- _validate_image_filename (no sanitizer fallback) ---

    async def test_no_sanitizer_blocks_path_traversal(self, tmp_path):
        """When sanitizer=None the inline check still blocks path traversal."""
        client = ComfyUIClient(base_url="http://test:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(mode="audit", dangerous_nodes=[], allowed_nodes=[])
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="path traversal"):
            await tools["transform_image"](image="../evil.png", prompt="p")

    async def test_no_sanitizer_blocks_null_byte(self, tmp_path):
        client = ComfyUIClient(base_url="http://test:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(mode="audit", dangerous_nodes=[], allowed_nodes=[])
        mcp = FastMCP("test")
        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="null byte"):
            await tools["transform_image"](image="evil\x00.png", prompt="p")
