import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.config import ModelSearchSettings, Settings
from comfyui_mcp.model_manager import ModelManagerDetector
from comfyui_mcp.security.download_validator import DownloadValidator
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
from comfyui_mcp.server import _build_server
from comfyui_mcp.tools.models import register_model_tools


@pytest.fixture
def components(tmp_path):
    client = ComfyUIClient(base_url="http://test:8188")
    audit = AuditLogger(audit_file=tmp_path / "audit.log")
    read_limiter = RateLimiter(max_per_minute=60)
    file_limiter = RateLimiter(max_per_minute=30)
    sanitizer = PathSanitizer(
        allowed_extensions=[".safetensors", ".ckpt", ".pt", ".pth", ".bin"],
        max_size_mb=50,
    )
    detector = ModelManagerDetector(client)
    validator = DownloadValidator(
        allowed_domains=["huggingface.co", "civitai.com"],
        allowed_extensions=[".safetensors", ".ckpt", ".pt", ".pth", ".bin"],
    )
    search_settings = ModelSearchSettings()
    return {
        "client": client,
        "audit": audit,
        "read_limiter": read_limiter,
        "file_limiter": file_limiter,
        "sanitizer": sanitizer,
        "detector": detector,
        "validator": validator,
        "search_settings": search_settings,
    }


@pytest.fixture
def registered_tools(components):
    mcp = FastMCP("test")
    tools = register_model_tools(
        mcp=mcp,
        client=components["client"],
        audit=components["audit"],
        read_limiter=components["read_limiter"],
        file_limiter=components["file_limiter"],
        sanitizer=components["sanitizer"],
        detector=components["detector"],
        validator=components["validator"],
        search_settings=components["search_settings"],
    )
    return tools


class TestSearchModels:
    @respx.mock
    async def test_search_civitai(self, registered_tools):
        respx.get("https://civitai.com/api/v1/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": 1,
                            "name": "Epic Realism",
                            "type": "Checkpoint",
                            "stats": {"downloadCount": 50000, "rating": 4.8},
                            "modelVersions": [
                                {
                                    "id": 100,
                                    "name": "v5",
                                    "downloadUrl": "https://civitai.com/api/download/models/100",
                                    "files": [
                                        {"sizeKB": 2048000, "name": "epicrealism_v5.safetensors"}
                                    ],
                                }
                            ],
                        }
                    ],
                    "metadata": {"totalItems": 1},
                },
            )
        )
        result = await registered_tools["search_models"](query="epic realism", source="civitai")
        parsed = json.loads(result)
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["name"] == "Epic Realism"

    @respx.mock
    async def test_search_huggingface(self, registered_tools):
        respx.get("https://huggingface.co/api/models").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "stabilityai/sdxl",
                        "modelId": "stabilityai/sdxl",
                        "downloads": 1000000,
                        "pipeline_tag": "text-to-image",
                        "tags": ["diffusers", "safetensors"],
                        "likes": 500,
                    }
                ],
            )
        )
        respx.get("https://huggingface.co/api/models/stabilityai/sdxl").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "stabilityai/sdxl",
                    "siblings": [
                        {"rfilename": "model.safetensors", "size": 6800000000},
                        {"rfilename": "README.md", "size": 1000},
                    ],
                },
            )
        )
        result = await registered_tools["search_models"](query="sdxl", source="huggingface")
        parsed = json.loads(result)
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["name"] == "stabilityai/sdxl"

    @respx.mock
    async def test_search_invalid_source(self, registered_tools):
        with pytest.raises(ValueError, match="source must be"):
            await registered_tools["search_models"](query="test", source="invalid")

    async def test_search_empty_query_rejected(self, registered_tools):
        with pytest.raises(ValueError, match="must not be empty"):
            await registered_tools["search_models"](query="", source="civitai")

    async def test_search_whitespace_query_rejected(self, registered_tools):
        with pytest.raises(ValueError, match="must not be empty"):
            await registered_tools["search_models"](query="   ", source="civitai")

    async def test_search_query_too_long_rejected(self, registered_tools):
        with pytest.raises(ValueError, match="query too long"):
            await registered_tools["search_models"](query="x" * 201, source="civitai")

    async def test_search_model_type_too_long_rejected(self, registered_tools):
        with pytest.raises(ValueError, match="model_type too long"):
            await registered_tools["search_models"](
                query="test", source="civitai", model_type="x" * 51
            )

    @respx.mock
    async def test_search_with_api_key(self, components):
        components["search_settings"] = ModelSearchSettings(civitai_api_key="test_key")
        mcp = FastMCP("test")
        tools = register_model_tools(
            mcp=mcp,
            client=components["client"],
            audit=components["audit"],
            read_limiter=components["read_limiter"],
            file_limiter=components["file_limiter"],
            sanitizer=components["sanitizer"],
            detector=components["detector"],
            validator=components["validator"],
            search_settings=components["search_settings"],
        )
        route = respx.get("https://civitai.com/api/v1/models").mock(
            return_value=httpx.Response(200, json={"items": [], "metadata": {"totalItems": 0}})
        )
        await tools["search_models"](query="test", source="civitai")
        assert route.calls[0].request.headers.get("authorization") == "Bearer test_key"


class TestDownloadModel:
    @respx.mock
    async def test_download_valid_model(self, registered_tools):
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
        respx.post("http://test:8188/model-manager/model").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"taskId": "t-1"}})
        )
        result = await registered_tools["download_model"](
            url="https://civitai.com/api/download/models/12345",
            folder="checkpoints",
            filename="epicrealism.safetensors",
        )
        parsed = json.loads(result)
        assert parsed["taskId"] == "t-1"

    @respx.mock
    async def test_download_blocked_domain(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        with pytest.raises(Exception, match="not in allowed domains"):
            await registered_tools["download_model"](
                url="https://evil.com/model.safetensors",
                folder="checkpoints",
                filename="model.safetensors",
            )

    @respx.mock
    async def test_download_bad_extension(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        with pytest.raises(Exception, match="extension"):
            await registered_tools["download_model"](
                url="https://civitai.com/api/download/models/123",
                folder="checkpoints",
                filename="model.exe",
            )

    @respx.mock
    async def test_download_invalid_folder(self, registered_tools):
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
        with pytest.raises(ValueError, match="not a valid model folder"):
            await registered_tools["download_model"](
                url="https://civitai.com/api/download/models/123",
                folder="invalid_folder",
                filename="model.safetensors",
            )

    @respx.mock
    async def test_download_model_manager_unavailable(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(return_value=httpx.Response(404))
        with pytest.raises(Exception, match="not detected"):
            await registered_tools["download_model"](
                url="https://civitai.com/api/download/models/123",
                folder="checkpoints",
                filename="model.safetensors",
            )

    @respx.mock
    async def test_download_infers_platform_huggingface(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "data": {"checkpoints": ["/models/checkpoints"]}},
            )
        )
        route = respx.post("http://test:8188/model-manager/model").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"taskId": "t-1"}})
        )
        await registered_tools["download_model"](
            url="https://huggingface.co/org/repo/resolve/main/model.safetensors",
            folder="checkpoints",
            filename="model.safetensors",
        )
        body = route.calls[0].request.content.decode()
        assert "huggingface" in body


class TestGetDownloadTasks:
    @respx.mock
    async def test_get_tasks(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "data": {"checkpoints": ["/models/checkpoints"]}},
            )
        )
        respx.get("http://test:8188/model-manager/download/task").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {
                            "taskId": "t1",
                            "status": "doing",
                            "progress": 75,
                            "totalSize": 1000,
                            "downloadedSize": 750,
                        }
                    ],
                },
            )
        )
        result = await registered_tools["get_download_tasks"]()
        parsed = json.loads(result)
        assert len(parsed["tasks"]) == 1


class TestCancelDownload:
    @respx.mock
    async def test_cancel_task(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        respx.delete("http://test:8188/model-manager/download/task-1").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        result = await registered_tools["cancel_download"](task_id="task-1")
        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["task_id"] == "task-1"
        assert parsed["result"] == {"success": True}


class TestServerWiring:
    def test_model_tools_registered(self):
        """Verify that _register_all_tools accepts the new parameters."""
        server, _settings = _build_server(settings=Settings())
        assert server is not None
