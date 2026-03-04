"""Tests for node danger auditor."""

from comfyui_mcp.security.node_auditor import (
    NodeAuditor,
)


class TestNodeAuditor:
    def test_audits_dangerous_name_patterns(self):
        auditor = NodeAuditor()

        node_info = {
            "input": {},
            "output": ["STRING"],
            "description": "Executes python code",
        }

        result = auditor.audit_node_class("RunPython", node_info)
        assert result is not None
        assert result.category == "dangerous"
        assert "python" in result.reason.lower()

    def test_audits_python_node(self):
        auditor = NodeAuditor()

        node_info = {"input": {}, "output": ["STRING"]}

        result = auditor.audit_node_class("RunPython", node_info)
        assert result is not None
        assert result.category == "dangerous"

    def test_audits_dangerous_input_type(self):
        auditor = NodeAuditor()

        node_info = {
            "input": {
                "code": {
                    "type": "CODE",
                    "required": True,
                }
            },
            "output": ["STRING"],
        }

        result = auditor.audit_node_class("SafeLookingNode", node_info)
        assert result is not None
        assert result.category == "dangerous"
        assert "CODE" in result.reason

    def test_audits_suspicious_by_description(self):
        auditor = NodeAuditor()

        node_info = {
            "input": {"text": {"type": "STRING"}},
            "output": ["STRING"],
            "description": "Can execute arbitrary code in your workflow",
        }

        result = auditor.audit_node_class("SomeWildcardNode", node_info)
        assert result is not None
        assert result.category == "suspicious"

    def test_safe_node_returns_none(self):
        auditor = NodeAuditor()

        node_info = {
            "input": {"text": {"type": "STRING"}},
            "output": ["IMAGE"],
            "description": "A simple text encoder",
        }

        result = auditor.audit_node_class("CLIPTextEncode", node_info)
        assert result is None

    def test_handles_list_input_type(self):
        auditor = NodeAuditor()

        node_info = {
            "input": {
                "text": ["STRING", "STRING"],  # Some nodes have list types
            },
            "output": ["STRING"],
        }

        result = auditor.audit_node_class("SomeNode", node_info)
        assert result is None

    def test_handles_missing_input(self):
        auditor = NodeAuditor()

        node_info = {"output": ["STRING"]}

        result = auditor.audit_node_class("SomeNode", node_info)
        assert result is None

    def test_handles_missing_description(self):
        auditor = NodeAuditor()

        node_info = {"input": {}, "output": ["STRING"]}

        result = auditor.audit_node_class("SomeNode", node_info)
        assert result is None


class TestAuditAllNodes:
    def test_audits_full_node_list(self):
        auditor = NodeAuditor()

        object_info = {
            "KSampler": {
                "input": {"seed": {"type": "INT"}},
                "output": ["LATENT"],
            },
            "RunPython": {
                "input": {"code": {"type": "CODE"}},
                "output": ["*"],
            },
            "CLIPTextEncode": {
                "input": {"text": {"type": "STRING"}},
                "output": ["CLIP"],
            },
        }

        result = auditor.audit_all_nodes(object_info)

        assert result.total_nodes == 3
        assert result.dangerous_count == 1
        assert result.suspicious_count == 0
        assert result.dangerous_nodes[0].node_class == "RunPython"

    def test_empty_node_list(self):
        auditor = NodeAuditor()

        result = auditor.audit_all_nodes({})

        assert result.total_nodes == 0
        assert result.dangerous_count == 0
        assert result.suspicious_count == 0

    def test_filters_non_dict_nodes(self):
        auditor = NodeAuditor()

        object_info = {
            "ValidNode": {"input": {}},
            "InvalidNode": "not a dict",
        }

        result = auditor.audit_all_nodes(object_info)

        assert result.total_nodes == 2
        assert result.dangerous_count == 0
