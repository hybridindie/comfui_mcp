"""Tests for workflow composition MCP tools."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.tools.workflow import register_workflow_tools


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    inspector = WorkflowInspector(mode="audit", dangerous_nodes=["EvalNode"], allowed_nodes=[])
    return client, audit, limiter, inspector


class TestCreateWorkflow:
    async def test_creates_txt2img(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        result = await tools["create_workflow"](template="txt2img")
        wf = json.loads(result)
        class_types = {v["class_type"] for v in wf.values()}
        assert "KSampler" in class_types
        assert "CheckpointLoaderSimple" in class_types

    async def test_creates_with_params(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        params = json.dumps({"prompt": "a dog", "steps": 30})
        result = await tools["create_workflow"](template="txt2img", params=params)
        wf = json.loads(result)
        sampler = next(v for v in wf.values() if v["class_type"] == "KSampler")
        assert sampler["inputs"]["steps"] == 30

    async def test_invalid_template_raises(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="Unknown template"):
            await tools["create_workflow"](template="nonexistent")

    async def test_audit_log_written(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        await tools["create_workflow"](template="txt2img")
        log_lines = audit._audit_file.read_text().strip().split("\n")
        entries = [json.loads(line) for line in log_lines]
        assert any(e["tool"] == "create_workflow" for e in entries)


class TestModifyWorkflow:
    async def test_adds_node(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        wf = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        ops = json.dumps([{"op": "add_node", "class_type": "SaveImage"}])
        result = await tools["modify_workflow"](workflow=wf, operations=ops)
        modified = json.loads(result)
        assert "2" in modified

    async def test_invalid_workflow_json_raises(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        ops = json.dumps([{"op": "add_node", "class_type": "SaveImage"}])
        with pytest.raises(ValueError, match="Invalid JSON"):
            await tools["modify_workflow"](workflow="not json", operations=ops)

    async def test_invalid_operations_json_raises(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        wf = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        with pytest.raises(ValueError, match="Invalid JSON"):
            await tools["modify_workflow"](workflow=wf, operations="not json")


class TestValidateWorkflow:
    @respx.mock
    async def test_valid_workflow(self, components):
        client, audit, limiter, inspector = components
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "KSampler": {"display_name": "KSampler", "input": {"required": {}}},
                },
            )
        )
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        wf = json.dumps({"1": {"class_type": "KSampler", "inputs": {}}})
        result = await tools["validate_workflow"](workflow=wf)
        parsed = json.loads(result)
        assert parsed["valid"] is True

    async def test_invalid_json_raises(self, components):
        client, audit, limiter, inspector = components
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)
        with pytest.raises(ValueError, match="Invalid JSON"):
            await tools["validate_workflow"](workflow="not json")


class TestIntegration:
    @respx.mock
    async def test_create_modify_validate_roundtrip(self, components):
        client, audit, limiter, inspector = components
        respx.get("http://test:8188/object_info").mock(side_effect=httpx.ConnectError("offline"))
        mcp = FastMCP("test")
        tools = register_workflow_tools(mcp, client, audit, limiter, inspector)

        # Create
        created = await tools["create_workflow"](
            template="txt2img", params=json.dumps({"prompt": "a cat"})
        )
        wf = json.loads(created)

        # Modify — add a LoRA loader
        ops = json.dumps(
            [
                {
                    "op": "add_node",
                    "node_id": "20",
                    "class_type": "LoraLoader",
                    "inputs": {"lora_name": "detail.safetensors"},
                },
            ]
        )
        modified = await tools["modify_workflow"](workflow=json.dumps(wf), operations=ops)
        mod_wf = json.loads(modified)
        assert "20" in mod_wf

        # Validate
        validated = await tools["validate_workflow"](workflow=modified)
        result = json.loads(validated)
        assert result["node_count"] == len(mod_wf)
