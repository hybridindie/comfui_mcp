import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.config import ModelSearchSettings
from comfyui_mcp.model_manager import ModelManagerDetector
from comfyui_mcp.security.download_validator import DownloadValidator
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer
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
