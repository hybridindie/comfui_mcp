"""Tests for server initialization and tool registration."""

from comfyui_mcp.config import ComfyUISettings, Settings
from comfyui_mcp.server import _build_server


class TestServerSetup:
    def test_server_has_name(self):
        settings = Settings(comfyui=ComfyUISettings(url="http://test:8188"))
        server, *_ = _build_server(settings)
        assert server.name == "ComfyUI"

    def test_build_server_returns_settings(self):
        settings = Settings(comfyui=ComfyUISettings(url="http://test:8188"))
        _, returned_settings, *_ = _build_server(settings)
        assert returned_settings.comfyui.url == "http://test:8188"
