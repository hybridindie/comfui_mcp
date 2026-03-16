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
            return_value=httpx.Response(
                200, json={"prompt_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
            )
        )
        result = await client.post_prompt({"1": {"class_type": "KSampler", "inputs": {}}})
        assert result["prompt_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

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
        await client.delete_queue_item("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    @respx.mock
    async def test_get_history_item(self, client):
        respx.get("http://test-comfyui:8188/history/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee").mock(
            return_value=httpx.Response(
                200, json={"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": {"outputs": {}}}
            )
        )
        result = await client.get_history_item("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in result

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
    async def test_get_system_stats(self, client):
        payload = {"system": {"comfyui_version": "0.3.10"}, "devices": []}
        respx.get("http://test-comfyui:8188/system_stats").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.get_system_stats()
        assert result["system"]["comfyui_version"] == "0.3.10"

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


class TestModelManagerClient:
    @respx.mock
    async def test_get_model_manager_folders(self, client):
        respx.get("http://test-comfyui:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "vae": ["/models/vae"],
                        "loras": ["/models/loras"],
                        "checkpoints": ["/models/checkpoints"],
                    },
                },
            )
        )
        result = await client.get_model_manager_folders()
        assert result == ["checkpoints", "loras", "vae"]

    @respx.mock
    async def test_create_download_task(self, client):
        route = respx.post("http://test-comfyui:8188/model-manager/model").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"taskId": "task-1"}})
        )
        result = await client.create_download_task(
            model_type="checkpoints",
            path_index=0,
            fullname="model.safetensors",
            download_platform="huggingface",
            download_url="https://huggingface.co/org/repo/resolve/main/model.safetensors",
            size_bytes=1000000,
        )
        assert result["taskId"] == "task-1"
        body = route.calls[0].request.content.decode()
        assert "previewFile=" in body

    @respx.mock
    async def test_get_download_tasks(self, client):
        respx.get("http://test-comfyui:8188/model-manager/download/task").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [{"taskId": "t1", "status": "doing", "progress": 50}],
                },
            )
        )
        result = await client.get_download_tasks()
        assert len(result) == 1
        assert result[0]["taskId"] == "t1"

    @respx.mock
    async def test_delete_download_task(self, client):
        respx.delete("http://test-comfyui:8188/model-manager/download/task-1").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "data": {"taskId": "task-1", "removed": True}},
            )
        )
        result = await client.delete_download_task("task-1")
        assert result == {"taskId": "task-1", "removed": True}


class TestPathInjectionValidation:
    """Verify that prompt_id and path segment validators block injection attempts."""

    async def test_get_history_item_rejects_path_traversal(self, client):
        with pytest.raises(ValueError, match="Invalid prompt_id"):
            await client.get_history_item("../../../free")

    async def test_get_history_item_rejects_empty(self, client):
        with pytest.raises(ValueError, match="Invalid prompt_id"):
            await client.get_history_item("")

    async def test_get_history_item_rejects_non_uuid(self, client):
        with pytest.raises(ValueError, match="Invalid prompt_id"):
            await client.get_history_item("not-a-valid-uuid-format")

    async def test_delete_queue_item_rejects_path_traversal(self, client):
        with pytest.raises(ValueError, match="Invalid prompt_id"):
            await client.delete_queue_item("../../userdata")

    async def test_get_object_info_rejects_path_traversal(self, client):
        with pytest.raises(ValueError, match="invalid characters"):
            await client.get_object_info("../../userdata")

    async def test_get_object_info_rejects_slash(self, client):
        with pytest.raises(ValueError, match="invalid characters"):
            await client.get_object_info("node/traversal")

    async def test_get_object_info_rejects_empty(self, client):
        with pytest.raises(ValueError, match="must not be empty"):
            await client.get_object_info("")

    async def test_delete_download_task_rejects_path_traversal(self, client):
        with pytest.raises(ValueError, match="invalid characters"):
            await client.delete_download_task("../../free")

    async def test_delete_download_task_rejects_empty(self, client):
        with pytest.raises(ValueError, match="must not be empty"):
            await client.delete_download_task("")

    @respx.mock
    async def test_valid_uuid_passes_through(self, client):
        """Sanity check: valid UUID is accepted."""
        respx.get("http://test-comfyui:8188/history/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee").mock(
            return_value=httpx.Response(200, json={})
        )
        result = await client.get_history_item("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert isinstance(result, dict)

    @respx.mock
    async def test_valid_node_class_passes_through(self, client):
        """Sanity check: valid node class name is accepted."""
        respx.get("http://test-comfyui:8188/object_info/KSampler").mock(
            return_value=httpx.Response(200, json={"KSampler": {}})
        )
        result = await client.get_object_info("KSampler")
        assert "KSampler" in result


class TestComfyUIManagerClient:
    @respx.mock
    async def test_get_manager_version(self, client):
        respx.get("http://test-comfyui:8188/manager/version").mock(
            return_value=httpx.Response(200, text="1.0.0")
        )
        result = await client.get_manager_version()
        assert result == "1.0.0"

    @respx.mock
    async def test_get_custom_node_list(self, client):
        payload = {
            "channel": "default",
            "node_packs": {
                "comfyui-impact-pack": {
                    "title": "Impact Pack",
                    "installed": "True",
                }
            },
        }
        respx.get("http://test-comfyui:8188/customnode/getlist").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.get_custom_node_list()
        assert result["channel"] == "default"
        assert "comfyui-impact-pack" in result["node_packs"]

    @respx.mock
    async def test_queue_custom_node_install(self, client):
        route = respx.post("http://test-comfyui:8188/manager/queue/install").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.queue_custom_node_install("comfyui-impact-pack")
        body = json.loads(route.calls[0].request.content)
        assert body["id"] == "comfyui-impact-pack"

    @respx.mock
    async def test_queue_custom_node_uninstall(self, client):
        route = respx.post("http://test-comfyui:8188/manager/queue/uninstall").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.queue_custom_node_uninstall("comfyui-impact-pack")
        body = json.loads(route.calls[0].request.content)
        assert body["id"] == "comfyui-impact-pack"

    @respx.mock
    async def test_queue_custom_node_update(self, client):
        route = respx.post("http://test-comfyui:8188/manager/queue/update").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.queue_custom_node_update("comfyui-impact-pack")
        body = json.loads(route.calls[0].request.content)
        assert body["id"] == "comfyui-impact-pack"

    @respx.mock
    async def test_start_custom_node_queue(self, client):
        respx.get("http://test-comfyui:8188/manager/queue/start").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.start_custom_node_queue()

    @respx.mock
    async def test_get_custom_node_queue_status(self, client):
        payload = {
            "is_processing": True,
            "total_count": 3,
            "processed_count": 1,
            "current_action": "installing comfyui-impact-pack",
        }
        respx.get("http://test-comfyui:8188/manager/queue/status").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.get_custom_node_queue_status()
        assert result["is_processing"] is True
        assert result["total_count"] == 3
        assert result["processed_count"] == 1

    @respx.mock
    async def test_reboot_comfyui(self, client):
        respx.get("http://test-comfyui:8188/manager/reboot").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.reboot_comfyui()
