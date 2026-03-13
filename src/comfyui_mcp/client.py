"""Async HTTP client for ComfyUI API."""

from __future__ import annotations

import asyncio
import re

import httpx

_ALLOWED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _validate_prompt_id(prompt_id: str) -> str:
    """Validate that a prompt_id is a well-formed UUID."""
    if not _UUID_RE.match(prompt_id):
        raise ValueError(f"Invalid prompt_id format: {prompt_id!r}")
    return prompt_id


def _validate_path_segment(value: str, *, label: str = "value") -> str:
    """Validate that a value is safe for interpolation into a URL path segment."""
    if not value:
        raise ValueError(f"{label} must not be empty")
    if not _SAFE_SEGMENT_RE.match(value):
        raise ValueError(f"{label} contains invalid characters: {value!r}")
    return value


class ComfyUIClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        timeout_connect: int = 30,
        timeout_read: int = 300,
        tls_verify: bool = True,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(connect=timeout_connect, read=timeout_read, write=30, pool=30)
        self._tls_verify = tls_verify
        self._client: httpx.AsyncClient | None = None
        self._max_retries = max_retries

    @property
    def base_url(self) -> str:
        """Return the base URL for the ComfyUI server."""
        return self._base_url

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                verify=self._tls_verify,
            )
        return self._client

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with retry logic for transient failures."""
        normalized = method.upper()
        if normalized not in _ALLOWED_HTTP_METHODS:
            raise ValueError(f"HTTP method not allowed: {method!r}")
        last_exception: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                c = await self._get_client()
                r = await c.request(normalized, path, **kwargs)
                r.raise_for_status()
                return r
            except httpx.HTTPStatusError:
                raise
            except httpx.RequestError as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                continue
        raise last_exception or RuntimeError("Request failed")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> ComfyUIClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @staticmethod
    def _unwrap_model_manager_response(payload: object) -> object:
        """Normalize ComfyUI-Model-Manager success envelopes to their data payload."""
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            return payload["data"]
        return payload

    async def get_queue(self) -> dict:
        r = await self._request("get", "/queue")
        return r.json()

    async def post_prompt(self, workflow: dict, *, client_id: str | None = None) -> dict:
        payload: dict = {"prompt": workflow}
        if client_id is not None:
            payload["client_id"] = client_id
        r = await self._request("post", "/prompt", json=payload)
        return r.json()

    async def get_models(self, folder: str) -> list:
        r = await self._request("get", f"/models/{folder}")
        return r.json()

    async def get_object_info(self, node_class: str | None = None) -> dict:
        if node_class is not None:
            _validate_path_segment(node_class, label="node_class")
        path = f"/object_info/{node_class}" if node_class else "/object_info"
        r = await self._request("get", path)
        return r.json()

    async def get_history(self) -> dict:
        r = await self._request("get", "/history")
        return r.json()

    async def get_history_item(self, prompt_id: str) -> dict:
        _validate_prompt_id(prompt_id)
        r = await self._request("get", f"/history/{prompt_id}")
        return r.json()

    async def interrupt(self) -> None:
        await self._request("post", "/interrupt")

    async def delete_queue_item(self, prompt_id: str) -> None:
        _validate_prompt_id(prompt_id)
        await self._request("post", "/queue", json={"delete": [prompt_id]})

    async def upload_image(self, data: bytes, filename: str, subfolder: str = "") -> dict:
        files = {"image": (filename, data, "image/png")}
        form_data: dict[str, str] = {}
        if subfolder:
            form_data["subfolder"] = subfolder
        r = await self._request("post", "/upload/image", files=files, data=form_data)
        return r.json()

    async def get_image(self, filename: str, subfolder: str = "output") -> tuple[bytes, str]:
        r = await self._request(
            "get", "/view", params={"filename": filename, "subfolder": subfolder}
        )
        content_type = r.headers.get("content-type", "image/png")
        return r.content, content_type

    async def get_embeddings(self) -> list:
        r = await self._request("get", "/embeddings")
        return r.json()

    async def get_workflow_templates(self) -> list:
        r = await self._request("get", "/workflow_templates")
        return r.json()

    async def get_extensions(self) -> list:
        r = await self._request("get", "/extensions")
        return r.json()

    async def get_features(self) -> dict:
        r = await self._request("get", "/features")
        return r.json()

    async def get_model_types(self) -> list:
        r = await self._request("get", "/models")
        return r.json()

    async def get_view_metadata(self, folder: str, filename: str) -> dict:
        r = await self._request("get", f"/view_metadata/{folder}", params={"filename": filename})
        return r.json()

    async def get_prompt_status(self) -> dict:
        r = await self._request("get", "/prompt")
        return r.json()

    async def get_system_stats(self) -> dict:
        """GET /system_stats — raw ComfyUI system statistics.

        NOTE: /system_stats is on the blocked-endpoint list for direct exposure.
        This method is called exclusively by the get_system_info tool, which
        applies a strict whitelist before returning any data. No raw response
        is ever forwarded to callers. Do not add any other callers.
        """
        r = await self._request("get", "/system_stats")
        return r.json()

    async def clear_queue(self, clear_running: bool = False, clear_pending: bool = False) -> None:
        data: dict[str, list[str]] = {"clear": []}
        if clear_running:
            data["clear"].append("running")
        if clear_pending:
            data["clear"].append("pending")
        await self._request("post", "/queue", json=data)

    async def upload_mask(self, data: bytes, filename: str, subfolder: str = "") -> dict:
        files = {"mask": (filename, data, "image/png")}
        form_data: dict[str, str] = {}
        if subfolder:
            form_data["subfolder"] = subfolder
        r = await self._request("post", "/upload/mask", files=files, data=form_data)
        return r.json()

    # --- ComfyUI Manager endpoints ---

    async def get_manager_version(self) -> str:
        """GET /manager/version — check ComfyUI Manager availability."""
        r = await self._request("get", "/manager/version")
        return r.text

    async def get_custom_node_list(self, mode: str = "remote") -> dict:
        """GET /customnode/getlist — search/list registry nodes."""
        _validate_path_segment(mode, label="mode")
        r = await self._request("get", "/customnode/getlist", params={"mode": mode})
        return r.json()

    async def queue_custom_node_install(self, node_id: str, version: str = "") -> None:
        """POST /manager/queue/install — queue a node pack installation."""
        payload: dict[str, str] = {"id": node_id}
        if version:
            payload["version"] = version
        await self._request("post", "/manager/queue/install", json=payload)

    async def queue_custom_node_uninstall(self, node_id: str, version: str = "") -> None:
        """POST /manager/queue/uninstall — queue a node pack removal."""
        payload: dict[str, str] = {"id": node_id}
        if version:
            payload["version"] = version
        await self._request("post", "/manager/queue/uninstall", json=payload)

    async def queue_custom_node_update(self, node_id: str, version: str = "") -> None:
        """POST /manager/queue/update — queue a node pack update."""
        payload: dict[str, str] = {"id": node_id}
        if version:
            payload["version"] = version
        await self._request("post", "/manager/queue/update", json=payload)

    async def start_custom_node_queue(self) -> None:
        """GET /manager/queue/start — start processing queued tasks."""
        await self._request("get", "/manager/queue/start")

    async def get_custom_node_queue_status(self) -> dict:
        """GET /manager/queue/status — poll queue progress."""
        r = await self._request("get", "/manager/queue/status")
        return r.json()

    async def reboot_comfyui(self) -> None:
        """GET /manager/reboot — restart ComfyUI.

        NOTE: This endpoint uses GET (unusual for a destructive action) —
        this is upstream ComfyUI Manager behavior. Only called when the user
        explicitly passes restart=True and the job queue is verified empty.
        """
        await self._request("get", "/manager/reboot")

    # --- Model Manager endpoints ---

    async def get_model_manager_folders(self) -> list[str]:
        """GET /model-manager/models — list available model folder types."""
        r = await self._request("get", "/model-manager/models")
        payload = self._unwrap_model_manager_response(r.json())
        if isinstance(payload, dict):
            return sorted(payload.keys())
        if isinstance(payload, list):
            return payload
        raise TypeError("Unexpected response payload for /model-manager/models")

    async def create_download_task(
        self,
        *,
        model_type: str,
        path_index: int,
        fullname: str,
        download_platform: str,
        download_url: str,
        size_bytes: int,
        preview_url: str = "",
        description: str = "",
    ) -> dict:
        """POST /model-manager/model — create a model download task."""
        form_data = {
            "type": model_type,
            "pathIndex": str(path_index),
            "fullname": fullname,
            "downloadPlatform": download_platform,
            "downloadUrl": download_url,
            "sizeBytes": str(size_bytes),
            "previewFile": preview_url,
        }
        if description:
            form_data["description"] = description
        r = await self._request("post", "/model-manager/model", data=form_data)
        payload = self._unwrap_model_manager_response(r.json())
        if isinstance(payload, dict):
            return payload
        raise TypeError("Unexpected response payload for /model-manager/model")

    async def get_download_tasks(self) -> list[dict]:
        """GET /model-manager/download/task — list download tasks with progress."""
        r = await self._request("get", "/model-manager/download/task")
        payload = self._unwrap_model_manager_response(r.json())
        if isinstance(payload, list):
            return payload
        raise TypeError("Unexpected response payload for /model-manager/download/task")

    async def delete_download_task(self, task_id: str) -> dict:
        """DELETE /model-manager/download/{task_id} — cancel and remove a download."""
        _validate_path_segment(task_id, label="task_id")
        r = await self._request("delete", f"/model-manager/download/{task_id}")
        payload = self._unwrap_model_manager_response(r.json())
        if isinstance(payload, dict):
            return payload
        raise TypeError("Unexpected response payload for /model-manager/download/{task_id}")
