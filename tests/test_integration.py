"""End-to-end integration tests with mocked ComfyUI backend.

These tests wire up tool registration directly (via register_*_tools return dicts)
and exercise tools through the same code paths used in production.
"""

import json

import httpx
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.inspector import WorkflowBlockedError, WorkflowInspector
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
from comfyui_mcp.tools.discovery import register_discovery_tools
from comfyui_mcp.tools.generation import register_generation_tools
from comfyui_mcp.tools.jobs import register_job_tools


class TestImageGenerationFlow:
    @respx.mock
    async def test_generate_image_lists_models_then_generates(self, tmp_path):
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

        client = ComfyUIClient(base_url="http://mock-comfyui:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(mode="audit", dangerous_nodes=[], allowed_nodes=[])
        sanitizer = PathSanitizer(allowed_extensions=[".png", ".jpg", ".jpeg", ".webp"])
        mcp = FastMCP("test")

        discovery_tools = register_discovery_tools(mcp, client, audit, limiter, sanitizer)
        gen_tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        job_tools = register_job_tools(mcp, client, audit, limiter)

        # Step 1: Discover available models
        models = await discovery_tools["list_models"](folder="checkpoints")
        assert "sd_v15.safetensors" in models

        # Step 2: Generate an image
        result = await gen_tools["generate_image"](prompt="a sunset over mountains")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result

        # Step 3: Check the job
        job = await job_tools["get_job"](prompt_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in job

    @respx.mock
    async def test_run_workflow_with_dangerous_node_in_audit_mode(self, tmp_path):
        """Audit mode logs dangerous nodes but still submits the workflow."""
        respx.post("http://mock-comfyui:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "11111111-2222-3333-4444-555555555555"}
            )
        )

        client = ComfyUIClient(base_url="http://mock-comfyui:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(mode="audit", dangerous_nodes=["Terminal"], allowed_nodes=[])
        mcp = FastMCP("test")

        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = json.dumps({"1": {"class_type": "Terminal", "inputs": {}}})
        result = await tools["run_workflow"](workflow=workflow)
        assert "11111111-2222-3333-4444-555555555555" in result
        assert "Terminal" in result

    async def test_run_workflow_blocked_in_enforce_mode(self, tmp_path):
        """Enforce mode blocks workflows with unapproved nodes."""
        client = ComfyUIClient(base_url="http://mock-comfyui:8188")
        audit = AuditLogger(audit_file=tmp_path / "audit.log")
        limiter = RateLimiter(max_per_minute=60)
        inspector = WorkflowInspector(
            mode="enforce",
            dangerous_nodes=[],
            allowed_nodes=["KSampler", "CLIPTextEncode"],
        )
        mcp = FastMCP("test")

        tools = register_generation_tools(mcp, client, audit, limiter, inspector)
        workflow = json.dumps({"1": {"class_type": "MaliciousNode", "inputs": {}}})
        try:
            await tools["run_workflow"](workflow=workflow)
            raise AssertionError("Should have raised WorkflowBlockedError")
        except WorkflowBlockedError as e:
            assert "MaliciousNode" in str(e)
