"""Tests for generation and workflow execution MCP tools."""

import json

import pytest
import httpx
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.tools.generation import register_generation_tools
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.security.inspector import WorkflowInspector, WorkflowBlockedError
from comfyui_mcp.security.rate_limit import RateLimiter


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
        result = await tools["generate_image"](
            prompt="a beautiful sunset over mountains"
        )
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
