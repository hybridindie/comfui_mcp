import httpx
import pytest
import respx

from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.model_manager import ModelManagerDetector, ModelManagerUnavailableError


@pytest.fixture
def client():
    return ComfyUIClient(base_url="http://test:8188")


class TestModelManagerDetector:
    @respx.mock
    async def test_detect_available(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "checkpoints": ["/models/checkpoints"],
                        "loras": ["/models/loras"],
                        "vae": ["/models/vae"],
                    },
                },
            )
        )
        detector = ModelManagerDetector(client)
        folders = await detector.get_folders()
        assert "checkpoints" in folders
        assert "loras" in folders

    @respx.mock
    async def test_detect_unavailable(self, client):
        respx.get("http://test:8188/model-manager/models").mock(return_value=httpx.Response(404))
        detector = ModelManagerDetector(client)
        with pytest.raises(ModelManagerUnavailableError, match="not detected"):
            await detector.get_folders()

    @respx.mock
    async def test_caches_result(self, client):
        route = respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "data": {"checkpoints": ["/models/checkpoints"]}},
            )
        )
        detector = ModelManagerDetector(client)
        await detector.get_folders()
        await detector.get_folders()
        assert route.call_count == 1

    @respx.mock
    async def test_is_available_true(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "data": {"checkpoints": ["/models/checkpoints"]}},
            )
        )
        detector = ModelManagerDetector(client)
        assert await detector.is_available() is True

    @respx.mock
    async def test_is_available_false(self, client):
        respx.get("http://test:8188/model-manager/models").mock(return_value=httpx.Response(404))
        detector = ModelManagerDetector(client)
        assert await detector.is_available() is False

    @respx.mock
    async def test_validate_folder_known(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "checkpoints": ["/models/checkpoints"],
                        "loras": ["/models/loras"],
                    },
                },
            )
        )
        detector = ModelManagerDetector(client)
        await detector.validate_folder("checkpoints")  # Should not raise

    @respx.mock
    async def test_validate_folder_unknown(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "checkpoints": ["/models/checkpoints"],
                        "loras": ["/models/loras"],
                    },
                },
            )
        )
        detector = ModelManagerDetector(client)
        with pytest.raises(ValueError, match="not a valid model folder"):
            await detector.validate_folder("invalid_folder")
