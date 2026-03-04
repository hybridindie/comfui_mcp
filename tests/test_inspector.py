"""Tests for workflow inspection."""

import pytest

from comfyui_mcp.security.inspector import (
    WorkflowInspector,
    WorkflowBlockedError,
)


def _make_workflow(*node_types: str) -> dict:
    """Helper to build a minimal ComfyUI workflow dict."""
    workflow = {}
    for i, node_type in enumerate(node_types):
        workflow[str(i)] = {
            "class_type": node_type,
            "inputs": {},
        }
    return workflow


class TestWorkflowInspector:
    @pytest.fixture
    def audit_inspector(self):
        return WorkflowInspector(
            mode="audit",
            dangerous_nodes=["EvalNode", "ExecuteAnything"],
            allowed_nodes=[],
        )

    @pytest.fixture
    def enforce_inspector(self):
        return WorkflowInspector(
            mode="enforce",
            dangerous_nodes=["EvalNode"],
            allowed_nodes=["KSampler", "CLIPTextEncode", "VAEDecode", "SaveImage"],
        )

    def test_audit_mode_extracts_node_types(self, audit_inspector):
        workflow = _make_workflow("KSampler", "CLIPTextEncode", "VAEDecode")
        result = audit_inspector.inspect(workflow)
        assert set(result.nodes_used) == {"KSampler", "CLIPTextEncode", "VAEDecode"}

    def test_audit_mode_flags_dangerous_nodes(self, audit_inspector):
        workflow = _make_workflow("KSampler", "EvalNode")
        result = audit_inspector.inspect(workflow)
        assert len(result.warnings) > 0
        assert any("EvalNode" in w for w in result.warnings)

    def test_audit_mode_never_blocks(self, audit_inspector):
        workflow = _make_workflow("EvalNode", "ExecuteAnything")
        result = audit_inspector.inspect(workflow)
        assert len(result.warnings) > 0

    def test_enforce_mode_allows_approved_nodes(self, enforce_inspector):
        workflow = _make_workflow("KSampler", "CLIPTextEncode")
        result = enforce_inspector.inspect(workflow)
        assert len(result.warnings) == 0

    def test_enforce_mode_blocks_unapproved_nodes(self, enforce_inspector):
        workflow = _make_workflow("KSampler", "UnknownCustomNode")
        with pytest.raises(WorkflowBlockedError, match="UnknownCustomNode"):
            enforce_inspector.inspect(workflow)

    def test_enforce_mode_blocks_dangerous_nodes(self, enforce_inspector):
        workflow = _make_workflow("KSampler", "EvalNode")
        with pytest.raises(WorkflowBlockedError, match="EvalNode"):
            enforce_inspector.inspect(workflow)

    def test_empty_workflow(self, audit_inspector):
        result = audit_inspector.inspect({})
        assert result.nodes_used == []
        assert result.warnings == []

    def test_suspicious_input_flagged(self, audit_inspector):
        workflow = {
            "0": {
                "class_type": "KSampler",
                "inputs": {"code": "__import__('os').system('rm -rf /')"},
            }
        }
        result = audit_inspector.inspect(workflow)
        assert any("suspicious" in w.lower() for w in result.warnings)

    def test_suspicious_input_nested_in_dict(self, audit_inspector):
        workflow = {
            "0": {
                "class_type": "CustomNode",
                "inputs": {
                    "config": {"script": "exec('malicious')"},
                },
            }
        }
        result = audit_inspector.inspect(workflow)
        assert any("suspicious" in w.lower() for w in result.warnings)

    def test_suspicious_input_nested_in_list(self, audit_inspector):
        workflow = {
            "0": {
                "class_type": "CustomNode",
                "inputs": {
                    "scripts": ["safe", "__import__('os').system('whoami')"],
                },
            }
        }
        result = audit_inspector.inspect(workflow)
        assert any("suspicious" in w.lower() for w in result.warnings)
