"""Async HTTP client for ComfyUI API."""

from __future__ import annotations

import asyncio

import httpx


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
        last_exception: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                c = await self._get_client()
                r = await getattr(c, method)(path, **kwargs)
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
        path = f"/object_info/{node_class}" if node_class else "/object_info"
        r = await self._request("get", path)
        return r.json()

    async def get_history(self) -> dict:
        r = await self._request("get", "/history")
        return r.json()

    async def get_history_item(self, prompt_id: str) -> dict:
        r = await self._request("get", f"/history/{prompt_id}")
        return r.json()

    async def interrupt(self) -> None:
        await self._request("post", "/interrupt")

    async def delete_queue_item(self, prompt_id: str) -> None:
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

    # --- Model Manager endpoints ---

    async def get_model_manager_folders(self) -> list[str]:
        """GET /model-manager/models — list available model folder types."""
        r = await self._request("get", "/model-manager/models")
        payload = self._unwrap_model_manager_response(r.json())
        if isinstance(payload, dict):
            return list(payload.keys())
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
        r = await self._request("delete", f"/model-manager/download/{task_id}")
        return r.json()
