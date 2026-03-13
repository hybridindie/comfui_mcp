"""End-to-end integration tests with mocked ComfyUI backend.

These tests wire up the full server stack (config -> security -> tools -> client)
and exercise tools through the same code paths used in production, using the
public register_*_tools() return dicts (CLAUDE.md rule 12).
"""

import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowBlockedError, WorkflowInspector
from comfyui_mcp.security.model_checker import ModelChecker
from comfyui_mcp.security.node_auditor import NodeAuditor
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
from comfyui_mcp.tools.discovery import register_discovery_tools
from comfyui_mcp.tools.generation import register_generation_tools
from comfyui_mcp.tools.jobs import register_job_tools


@pytest.fixture
def integration_stack(tmp_path):
    """Build a full tool stack with real components, matching server.py wiring."""
    client = ComfyUIClient(base_url="http://mock-comfyui:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    gen_limiter = RateLimiter(max_per_minute=60)
    read_limiter = RateLimiter(max_per_minute=120)
    wf_limiter = RateLimiter(max_per_minute=30)
    inspector = WorkflowInspector(
        mode="audit",
        dangerous_nodes=["Terminal"],
        allowed_nodes=[],
    )
    sanitizer = PathSanitizer(
        allowed_extensions=[".png", ".jpg", ".jpeg", ".webp", ".gif", ".json"]
    )
    model_checker = ModelChecker()
    node_auditor = NodeAuditor()

    mcp = FastMCP("integration-test")

    discovery_tools = register_discovery_tools(
        mcp, client, audit, read_limiter, sanitizer, node_auditor
    )
    generation_tools = register_generation_tools(
        mcp,
        client,
        audit,
        gen_limiter,
        inspector,
        read_limiter=read_limiter,
        model_checker=model_checker,
    )
    job_tools = register_job_tools(mcp, client, audit, wf_limiter, read_limiter=read_limiter)

    return {
        **discovery_tools,
        **generation_tools,
        **job_tools,
    }


@pytest.fixture
def enforce_stack(tmp_path):
    """Stack with enforce mode for testing workflow blocking."""
    client = ComfyUIClient(base_url="http://mock-comfyui:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    limiter = RateLimiter(max_per_minute=60)
    inspector = WorkflowInspector(
        mode="enforce",
        dangerous_nodes=[],
        allowed_nodes=["KSampler", "CLIPTextEncode"],
    )
    mcp = FastMCP("integration-test-enforce")
    tools = register_generation_tools(mcp, client, audit, limiter, inspector)
    return tools


class TestImageGenerationFlow:
    @respx.mock
    async def test_generate_image_lists_models_then_generates(self, integration_stack):
        """Full flow: list models -> generate image -> check job."""
        respx.get("http://mock-comfyui:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["sd_v15.safetensors"])
        )
        respx.post("http://mock-comfyui:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )
        )
        respx.get("http://mock-comfyui:8188/history/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee").mock(
            return_value=httpx.Response(
                200,
                json={
                    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "comfyui-mcp_00001_.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        )

        # Step 1: Discover available models
        models = await integration_stack["list_models"](folder="checkpoints")
        assert "sd_v15.safetensors" in models

        # Step 2: Generate an image
        result = await integration_stack["generate_image"](prompt="a sunset over mountains")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result

        # Step 3: Check the job
        job = await integration_stack["get_job"](prompt_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in job

    @respx.mock
    async def test_run_workflow_with_dangerous_node_in_audit_mode(self, integration_stack):
        """Audit mode logs dangerous nodes but still submits the workflow."""
        respx.post("http://mock-comfyui:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "11111111-2222-3333-4444-555555555555"}
            )
        )

        workflow = json.dumps({"1": {"class_type": "Terminal", "inputs": {}}})
        result = await integration_stack["run_workflow"](workflow=workflow)
        assert "11111111-2222-3333-4444-555555555555" in result
        assert "Terminal" in result

    async def test_run_workflow_blocked_in_enforce_mode(self, enforce_stack):
        """Enforce mode blocks workflows with unapproved nodes."""
        workflow = json.dumps({"1": {"class_type": "MaliciousNode", "inputs": {}}})
        with pytest.raises(WorkflowBlockedError, match="MaliciousNode"):
            await enforce_stack["run_workflow"](workflow=workflow)
