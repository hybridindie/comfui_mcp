"""Tests for workflow validation."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowInspector
from comfyui_mcp.workflow.validation import validate_workflow


def _valid_workflow() -> dict[str, Any]:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "model.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "a cat", "clip": ["1", 1]},
        },
    }


@pytest.fixture
def client():
    return ComfyUIClient(base_url="http://test:8188")


@pytest.fixture
def inspector():
    return WorkflowInspector(mode="audit", dangerous_nodes=["EvalNode"], allowed_nodes=[])


class TestStructuralValidation:
    @respx.mock
    async def test_valid_workflow_passes(self, client, inspector):
        object_info = {
            "CheckpointLoaderSimple": {
                "display_name": "Load Checkpoint",
                "input": {"required": {"ckpt_name": [["model.safetensors"]]}},
            },
            "CLIPTextEncode": {
                "display_name": "CLIP Text Encode",
                "input": {"required": {"text": ["STRING"], "clip": ["CLIP"]}},
            },
        }
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(200, json=object_info)
        )
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["model.safetensors"])
        )
        result = await validate_workflow(_valid_workflow(), client, inspector)
        assert result["valid"] is True
        assert result["errors"] == []

    async def test_missing_class_type_is_error(self, client, inspector):
        wf = {"1": {"inputs": {"x": 1}}}
        result = await validate_workflow(wf, client, inspector)
        assert result["valid"] is False
        assert any("class_type" in e for e in result["errors"])

    async def test_broken_connection_is_error(self, client, inspector):
        wf = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"model": ["99", 0]},
            },
        }
        result = await validate_workflow(wf, client, inspector)
        assert result["valid"] is False
        assert any("99" in e for e in result["errors"])

    async def test_cycle_is_error(self, client, inspector):
        wf = {
            "1": {"class_type": "A", "inputs": {"x": ["2", 0]}},
            "2": {"class_type": "B", "inputs": {"x": ["1", 0]}},
        }
        result = await validate_workflow(wf, client, inspector)
        assert result["valid"] is False
        assert any("cycle" in e.lower() for e in result["errors"])


class TestServerValidation:
    @respx.mock
    async def test_missing_node_type_is_error(self, client, inspector):
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(
                200,
                json={
                    "CheckpointLoaderSimple": {
                        "display_name": "Load Checkpoint",
                        "input": {"required": {}},
                    },
                },
            )
        )
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["model.safetensors"])
        )
        wf = _valid_workflow()  # Has CLIPTextEncode which is NOT in object_info
        result = await validate_workflow(wf, client, inspector)
        assert result["valid"] is False
        assert any("CLIPTextEncode" in e and "not installed" in e for e in result["errors"])

    @respx.mock
    async def test_missing_model_is_warning(self, client, inspector):
        object_info = {
            "CheckpointLoaderSimple": {
                "display_name": "Load Checkpoint",
                "input": {"required": {"ckpt_name": [["other.safetensors"]]}},
            },
            "CLIPTextEncode": {
                "display_name": "CLIP Text Encode",
                "input": {"required": {"text": ["STRING"], "clip": ["CLIP"]}},
            },
        }
        respx.get("http://test:8188/object_info").mock(
            return_value=httpx.Response(200, json=object_info)
        )
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["other.safetensors"])
        )
        wf = _valid_workflow()  # Has model.safetensors which is NOT in models list
        result = await validate_workflow(wf, client, inspector)
        assert any("model.safetensors" in w for w in result["warnings"])

    @respx.mock
    async def test_server_unreachable_adds_warning(self, client, inspector):
        respx.get("http://test:8188/object_info").mock(side_effect=httpx.ConnectError("offline"))
        wf = _valid_workflow()
        result = await validate_workflow(wf, client, inspector)
        assert any("server" in w.lower() for w in result["warnings"])
        assert result["node_count"] == 2


class TestSecurityValidation:
    @respx.mock
    async def test_dangerous_node_adds_warning(self, client, inspector):
        respx.get("http://test:8188/object_info").mock(side_effect=httpx.ConnectError("offline"))
        wf = {"1": {"class_type": "EvalNode", "inputs": {}}}
        result = await validate_workflow(wf, client, inspector)
        assert any("Dangerous" in w for w in result["warnings"])

    @respx.mock
    async def test_enforce_mode_blocks(self, client):
        respx.get("http://test:8188/object_info").mock(side_effect=httpx.ConnectError("offline"))
        enforce_inspector = WorkflowInspector(
            mode="enforce",
            dangerous_nodes=[],
            allowed_nodes=["CheckpointLoaderSimple"],
        )
        wf = _valid_workflow()  # Has CLIPTextEncode which is not allowed
        result = await validate_workflow(wf, client, enforce_inspector)
        assert result["valid"] is False
        assert any("blocked" in e.lower() for e in result["errors"])
