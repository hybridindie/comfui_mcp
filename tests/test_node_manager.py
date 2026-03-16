"""Tests for ComfyUI Manager detector."""

import asyncio

import httpx
import pytest
import respx

from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.node_manager import ComfyUIManagerDetector, ComfyUIManagerUnavailableError


@pytest.fixture
def client():
    return ComfyUIClient(
        base_url="http://test-comfyui:8188",
        timeout_connect=5,
        timeout_read=10,
        tls_verify=False,
    )


class TestComfyUIManagerDetector:
    @respx.mock
    async def test_probe_success(self, client):
        """Detector reports available when /manager/version returns 200."""
        respx.get("http://test-comfyui:8188/manager/version").mock(
            return_value=httpx.Response(200, text="1.2.3")
        )
        detector = ComfyUIManagerDetector(client)
        result = await detector.is_available()
        assert result is True

    @respx.mock
    async def test_probe_failure_not_installed(self, client):
        """Detector reports unavailable when /manager/version returns 404."""
        respx.get("http://test-comfyui:8188/manager/version").mock(return_value=httpx.Response(404))
        detector = ComfyUIManagerDetector(client)
        result = await detector.is_available()
        assert result is False

    @respx.mock
    async def test_probe_caches_result(self, client):
        """Second call to is_available reuses cached result, no extra HTTP call."""
        route = respx.get("http://test-comfyui:8188/manager/version").mock(
            return_value=httpx.Response(200, text="1.2.3")
        )
        detector = ComfyUIManagerDetector(client)
        await detector.is_available()
        await detector.is_available()
        assert route.call_count == 1

    @respx.mock
    async def test_concurrent_probe_uses_lock(self, client):
        """Multiple concurrent is_available calls result in only one HTTP probe."""
        route = respx.get("http://test-comfyui:8188/manager/version").mock(
            return_value=httpx.Response(200, text="1.2.3")
        )
        detector = ComfyUIManagerDetector(client)
        results = await asyncio.gather(
            detector.is_available(),
            detector.is_available(),
            detector.is_available(),
        )
        assert all(r is True for r in results)
        assert route.call_count == 1

    @respx.mock
    async def test_require_available_raises_when_not_installed(self, client):
        """require_available raises ComfyUIManagerUnavailableError when Manager is absent."""
        respx.get("http://test-comfyui:8188/manager/version").mock(return_value=httpx.Response(404))
        detector = ComfyUIManagerDetector(client)
        with pytest.raises(ComfyUIManagerUnavailableError):
            await detector.require_available()

    @respx.mock
    async def test_error_message_includes_install_url(self, client):
        """The error message includes the GitHub install URL."""
        respx.get("http://test-comfyui:8188/manager/version").mock(return_value=httpx.Response(404))
        detector = ComfyUIManagerDetector(client)
        with pytest.raises(
            ComfyUIManagerUnavailableError,
            match=r"https://github\.com/Comfy-Org/ComfyUI-Manager",
        ):
            await detector.require_available()
