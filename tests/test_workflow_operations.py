"""Tests for workflow graph operations."""

from __future__ import annotations

from typing import Any

import pytest

from comfyui_mcp.workflow.operations import apply_operations


def _simple_workflow() -> dict[str, Any]:
    """A minimal 2-node workflow for testing."""
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


class TestAddNode:
    def test_add_node_with_explicit_id(self):
        wf = _simple_workflow()
        ops = [
            {
                "op": "add_node",
                "node_id": "10",
                "class_type": "VAEDecode",
                "inputs": {"samples": ["1", 0]},
            }
        ]
        result = apply_operations(wf, ops)
        assert "10" in result
        assert result["10"]["class_type"] == "VAEDecode"
        assert result["10"]["inputs"]["samples"] == ["1", 0]

    def test_add_node_auto_generates_id(self):
        wf = _simple_workflow()
        ops = [{"op": "add_node", "class_type": "SaveImage"}]
        result = apply_operations(wf, ops)
        assert "3" in result
        assert result["3"]["class_type"] == "SaveImage"

    def test_add_node_default_empty_inputs(self):
        wf = _simple_workflow()
        ops = [{"op": "add_node", "class_type": "VAEDecode"}]
        result = apply_operations(wf, ops)
        assert result["3"]["inputs"] == {}

    def test_add_node_duplicate_id_raises(self):
        wf = _simple_workflow()
        ops = [{"op": "add_node", "node_id": "1", "class_type": "SaveImage"}]
        with pytest.raises(ValueError, match="already exists"):
            apply_operations(wf, ops)

    def test_add_node_missing_class_type_raises(self):
        wf = _simple_workflow()
        ops = [{"op": "add_node"}]
        with pytest.raises(ValueError, match="class_type"):
            apply_operations(wf, ops)
