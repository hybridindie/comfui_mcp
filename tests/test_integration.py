"""End-to-end integration tests with mocked ComfyUI backend.

These tests wire up the full server stack (config -> security -> tools -> client)
and exercise tools through the same code paths used in production.
"""

import json

import httpx
import respx

from comfyui_mcp.config import ComfyUISettings, SecuritySettings, Settings
from comfyui_mcp.security.inspector import WorkflowBlockedError
from comfyui_mcp.server import _build_server


class TestImageGenerationFlow:
    @respx.mock
    async def test_generate_image_lists_models_then_generates(self):
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

        settings = Settings(comfyui=ComfyUISettings(url="http://mock-comfyui:8188"))
        server, *_ = _build_server(settings)

        # Step 1: Discover available models
        tools = server._tool_manager._tools
        list_models_fn = tools["list_models"].fn
        models = await list_models_fn(folder="checkpoints")
        assert "sd_v15.safetensors" in models

        # Step 2: Generate an image
        generate_fn = tools["generate_image"].fn
        result = await generate_fn(prompt="a sunset over mountains")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result

        # Step 3: Check the job
        get_job_fn = tools["get_job"].fn
        job = await get_job_fn(prompt_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in job

    @respx.mock
    async def test_run_workflow_with_dangerous_node_in_audit_mode(self):
        """Audit mode logs dangerous nodes but still submits the workflow."""
        respx.post("http://mock-comfyui:8188/prompt").mock(
            return_value=httpx.Response(
                200, json={"prompt_id": "11111111-2222-3333-4444-555555555555"}
            )
        )

        settings = Settings(comfyui=ComfyUISettings(url="http://mock-comfyui:8188"))
        server, *_ = _build_server(settings)

        run_workflow_fn = server._tool_manager._tools["run_workflow"].fn
        workflow = json.dumps({"1": {"class_type": "Terminal", "inputs": {}}})
        result = await run_workflow_fn(workflow=workflow)
        assert "11111111-2222-3333-4444-555555555555" in result
        assert "Terminal" in result

    async def test_run_workflow_blocked_in_enforce_mode(self):
        """Enforce mode blocks workflows with unapproved nodes."""
        settings = Settings(
            comfyui=ComfyUISettings(url="http://mock-comfyui:8188"),
            security=SecuritySettings(
                mode="enforce",
                allowed_nodes=["KSampler", "CLIPTextEncode"],
            ),
        )
        server, *_ = _build_server(settings)

        run_workflow_fn = server._tool_manager._tools["run_workflow"].fn
        workflow = json.dumps({"1": {"class_type": "MaliciousNode", "inputs": {}}})
        try:
            await run_workflow_fn(workflow=workflow)
            raise AssertionError("Should have raised WorkflowBlockedError")
        except WorkflowBlockedError as e:
            assert "MaliciousNode" in str(e)
