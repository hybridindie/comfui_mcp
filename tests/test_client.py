"""Tests for ComfyUI HTTP client."""

import json

import httpx
import pytest
import respx

from comfyui_mcp.client import ComfyUIClient


@pytest.fixture
def client():
    return ComfyUIClient(
        base_url="http://test-comfyui:8188",
        timeout_connect=5,
        timeout_read=10,
        tls_verify=False,
    )


class TestComfyUIClient:
    @respx.mock
    async def test_get_queue(self, client):
        respx.get("http://test-comfyui:8188/queue").mock(
            return_value=httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        )
        result = await client.get_queue()
        assert "queue_running" in result

    @respx.mock
    async def test_post_prompt(self, client):
        respx.post("http://test-comfyui:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )
        result = await client.post_prompt({"1": {"class_type": "KSampler", "inputs": {}}})
        assert result["prompt_id"] == "abc-123"

    @respx.mock
    async def test_get_models(self, client):
        respx.get("http://test-comfyui:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["model_v1.safetensors", "model_v2.safetensors"])
        )
        result = await client.get_models("checkpoints")
        assert len(result) == 2

    @respx.mock
    async def test_get_history(self, client):
        respx.get("http://test-comfyui:8188/history").mock(
            return_value=httpx.Response(200, json={"abc": {"outputs": {}}})
        )
        result = await client.get_history()
        assert "abc" in result

    @respx.mock
    async def test_get_object_info(self, client):
        respx.get("http://test-comfyui:8188/object_info").mock(
            return_value=httpx.Response(200, json={"KSampler": {"input": {}}})
        )
        result = await client.get_object_info()
        assert "KSampler" in result

    @respx.mock
    async def test_interrupt(self, client):
        respx.post("http://test-comfyui:8188/interrupt").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.interrupt()

    @respx.mock
    async def test_upload_image(self, client):
        respx.post("http://test-comfyui:8188/upload/image").mock(
            return_value=httpx.Response(
                200, json={"name": "uploaded.png", "subfolder": "", "type": "input"}
            )
        )
        result = await client.upload_image(b"fake-png-data", "test.png")
        assert result["name"] == "uploaded.png"

    @respx.mock
    async def test_get_image(self, client):
        respx.get("http://test-comfyui:8188/view").mock(
            return_value=httpx.Response(
                200, content=b"fake-image-bytes", headers={"content-type": "image/png"}
            )
        )
        data, content_type = await client.get_image("output.png", "output")
        assert data == b"fake-image-bytes"
        assert content_type == "image/png"

    @respx.mock
    async def test_delete_queue_item(self, client):
        respx.post("http://test-comfyui:8188/queue").mock(return_value=httpx.Response(200, json={}))
        await client.delete_queue_item("abc-123")

    @respx.mock
    async def test_get_history_item(self, client):
        respx.get("http://test-comfyui:8188/history/abc-123").mock(
            return_value=httpx.Response(200, json={"abc-123": {"outputs": {}}})
        )
        result = await client.get_history_item("abc-123")
        assert "abc-123" in result

    @respx.mock
    async def test_get_embeddings(self, client):
        respx.get("http://test-comfyui:8188/embeddings").mock(
            return_value=httpx.Response(200, json=["embedding1.pt", "embedding2.pt"])
        )
        result = await client.get_embeddings()
        assert len(result) == 2

    @respx.mock
    async def test_get_extensions(self, client):
        respx.get("http://test-comfyui:8188/extensions").mock(
            return_value=httpx.Response(200, json=["ext1", "ext2"])
        )
        result = await client.get_extensions()
        assert len(result) == 2

    @respx.mock
    async def test_get_features(self, client):
        respx.get("http://test-comfyui:8188/features").mock(
            return_value=httpx.Response(200, json={"supports_preview_metadata": True})
        )
        result = await client.get_features()
        assert result["supports_preview_metadata"] is True

    @respx.mock
    async def test_get_model_types(self, client):
        respx.get("http://test-comfyui:8188/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        result = await client.get_model_types()
        assert len(result) == 3
        assert "checkpoints" in result

    @respx.mock
    async def test_get_view_metadata(self, client):
        respx.get("http://test-comfyui:8188/view_metadata/checkpoints").mock(
            return_value=httpx.Response(200, json={"filename": "model.safetensors", "size": 123456})
        )
        result = await client.get_view_metadata("checkpoints", "model.safetensors")
        assert result["filename"] == "model.safetensors"

    @respx.mock
    async def test_get_prompt_status(self, client):
        respx.get("http://test-comfyui:8188/prompt").mock(
            return_value=httpx.Response(200, json={"exec_info": {"queue_remaining": 0}})
        )
        result = await client.get_prompt_status()
        assert "exec_info" in result

    @respx.mock
    async def test_clear_queue_pending(self, client):
        route = respx.post("http://test-comfyui:8188/queue").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.clear_queue(clear_pending=True)
        assert json.loads(route.calls[0].request.content) == {"clear": ["pending"]}

    @respx.mock
    async def test_clear_queue_running(self, client):
        route = respx.post("http://test-comfyui:8188/queue").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.clear_queue(clear_running=True)
        assert json.loads(route.calls[0].request.content) == {"clear": ["running"]}

    @respx.mock
    async def test_clear_queue_both(self, client):
        route = respx.post("http://test-comfyui:8188/queue").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.clear_queue(clear_running=True, clear_pending=True)
        payload = json.loads(route.calls[0].request.content)
        assert "running" in payload["clear"]
        assert "pending" in payload["clear"]

    @respx.mock
    async def test_upload_mask(self, client):
        respx.post("http://test-comfyui:8188/upload/mask").mock(
            return_value=httpx.Response(
                200, json={"name": "mask.png", "subfolder": "", "type": "input"}
            )
        )
        result = await client.upload_mask(b"fake-mask-data", "mask.png")
        assert result["name"] == "mask.png"

    @respx.mock
    async def test_retry_on_connection_error(self, client):
        route = respx.get("http://test-comfyui:8188/queue")
        route.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, json={"queue_running": [], "queue_pending": []}),
        ]
        result = await client.get_queue()
        assert "queue_running" in result
        assert route.call_count == 2

    @respx.mock
    async def test_no_retry_on_http_error(self, client):
        route = respx.get("http://test-comfyui:8188/queue").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_queue()
        assert route.call_count == 1
