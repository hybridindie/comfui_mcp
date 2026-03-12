"""Lazy detector for ComfyUI-Model-Manager availability."""

from __future__ import annotations

import asyncio
import time

import httpx

from comfyui_mcp.client import ComfyUIClient

_NEGATIVE_TTL_SECONDS = 300  # Re-probe after 5 minutes on failure


class ModelManagerUnavailableError(Exception):
    """Raised when Model Manager is not installed or unreachable."""


class ModelManagerDetector:
    """Lazy-init detector that probes Model Manager on first use and caches the result.

    Uses asyncio.Lock to prevent concurrent probes from racing.
    Calls GET /model-manager/models once — the response both confirms availability
    and provides the folder list in a single round-trip.

    Positive results are cached permanently. Negative results expire after
    ``_NEGATIVE_TTL_SECONDS`` so a late-starting Model Manager is picked up
    without requiring a server restart.
    """

    _INSTALL_URL = "https://github.com/hayden-fr/ComfyUI-Model-Manager"

    def __init__(self, client: ComfyUIClient) -> None:
        self._client = client
        self._folders: list[str] | None = None
        self._checked = False
        self._available = False
        self._last_failure: float = 0.0
        self._lock = asyncio.Lock()

    def _should_reprobe(self) -> bool:
        """Return True if the negative cache has expired."""
        if self._available:
            return False
        if not self._checked:
            return True
        return (time.monotonic() - self._last_failure) >= _NEGATIVE_TTL_SECONDS

    async def _probe(self) -> None:
        """Probe Model Manager and cache the result."""
        async with self._lock:
            if self._checked and not self._should_reprobe():
                return
            try:
                self._folders = await self._client.get_model_manager_folders()
                self._available = True
                self._checked = True
            except (httpx.HTTPStatusError, httpx.RequestError):
                self._available = False
                self._checked = True
                self._last_failure = time.monotonic()

    async def is_available(self) -> bool:
        """Check if Model Manager is installed. Caches the result."""
        await self._probe()
        return self._available

    async def get_folders(self) -> list[str]:
        """Return cached folder list, or raise if Model Manager is unavailable."""
        await self._probe()
        if not self._available or self._folders is None:
            raise ModelManagerUnavailableError(
                f"ComfyUI-Model-Manager not detected. Install it from {self._INSTALL_URL}"
            )
        return self._folders

    async def validate_folder(self, folder: str) -> None:
        """Raise ValueError if folder is not in Model Manager's known folders."""
        folders = await self.get_folders()
        if folder not in folders:
            raise ValueError(
                f"'{folder}' is not a valid model folder. Available: {', '.join(sorted(folders))}"
            )
