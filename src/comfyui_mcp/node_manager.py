"""Lazy detector for ComfyUI Manager availability."""

from __future__ import annotations

import asyncio

import httpx

from comfyui_mcp.client import ComfyUIClient


class ComfyUIManagerUnavailableError(Exception):
    """Raised when ComfyUI Manager is not installed or unreachable."""


class ComfyUIManagerDetector:
    """Lazy-init detector that probes ComfyUI Manager on first use and caches the result.

    Uses asyncio.Lock to prevent concurrent probes from racing.
    Calls GET /manager/version once to confirm availability.
    """

    _INSTALL_URL = "https://github.com/Comfy-Org/ComfyUI-Manager"

    def __init__(self, client: ComfyUIClient) -> None:
        self._client = client
        self._version: str | None = None
        self._checked = False
        self._available = False
        self._lock = asyncio.Lock()

    async def _probe(self) -> None:
        """Probe ComfyUI Manager once and cache the result."""
        async with self._lock:
            if self._checked:
                return
            self._checked = True
            try:
                self._version = await self._client.get_manager_version()
                self._available = True
            except (httpx.HTTPStatusError, httpx.RequestError):
                self._available = False

    async def is_available(self) -> bool:
        """Check if ComfyUI Manager is installed. Caches the result."""
        await self._probe()
        return self._available

    async def require_available(self) -> None:
        """Raise ComfyUIManagerUnavailableError if Manager is not installed."""
        await self._probe()
        if not self._available:
            raise ComfyUIManagerUnavailableError(
                f"ComfyUI Manager not detected. Install it from {self._INSTALL_URL}"
            )
