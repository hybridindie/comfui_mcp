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
        self._timeout = httpx.Timeout(
            connect=timeout_connect, read=timeout_read, write=30, pool=30
        )
        self._tls_verify = tls_verify
        self._client: httpx.AsyncClient | None = None
        self._max_retries = max_retries

    def _get_headers(self) -> dict[str, str]:
        return {}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._get_headers(),
                timeout=self._timeout,
                verify=self._tls_verify,
            )
        return self._client

    async def _request_with_retry_with_retry(
        self, method: str, path: str, **kwargs
    ) -> httpx.Response:
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

    async def __aenter__(self) -> "ComfyUIClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _request_with_retry(
        self, method: str, path: str, **kwargs
    ) -> httpx.Response:
        """Make an HTTP request to the ComfyUI API."""
        c = await self._get_client()
        r = await getattr(c, method)(path, **kwargs)
        r.raise_for_status()
        return r

    async def get_queue(self) -> dict:
        r = await self._request_with_retry("get", "/queue")
        return r.json()

    async def post_prompt(self, workflow: dict) -> dict:
        r = await self._request_with_retry("post", "/prompt", json={"prompt": workflow})
        return r.json()

    async def get_models(self, folder: str) -> list:
        r = await self._request_with_retry("get", f"/models/{folder}")
        return r.json()

    async def get_object_info(self, node_class: str | None = None) -> dict:
        path = f"/object_info/{node_class}" if node_class else "/object_info"
        r = await self._request_with_retry("get", path)
        return r.json()

    async def get_history(self) -> dict:
        r = await self._request_with_retry("get", "/history")
        return r.json()

    async def get_history_item(self, prompt_id: str) -> dict:
        r = await self._request_with_retry("get", f"/history/{prompt_id}")
        return r.json()

    async def interrupt(self) -> None:
        await self._request_with_retry("post", "/interrupt")

    async def delete_queue_item(self, prompt_id: str) -> None:
        await self._request_with_retry("post", "/queue", json={"delete": [prompt_id]})

    async def upload_image(
        self, data: bytes, filename: str, subfolder: str = ""
    ) -> dict:
        files = {"image": (filename, data, "image/png")}
        form_data: dict[str, str] = {}
        if subfolder:
            form_data["subfolder"] = subfolder
        r = await self._request_with_retry(
            "post", "/upload/image", files=files, data=form_data
        )
        return r.json()

    async def get_image(
        self, filename: str, subfolder: str = "output"
    ) -> tuple[bytes, str]:
        r = await self._request_with_retry(
            "get", "/view", params={"filename": filename, "subfolder": subfolder}
        )
        content_type = r.headers.get("content-type", "image/png")
        return r.content, content_type

    async def get_embeddings(self) -> list:
        r = await self._request_with_retry("get", "/embeddings")
        return r.json()

    async def get_workflow_templates(self) -> list:
        r = await self._request_with_retry("get", "/workflow_templates")
        return r.json()

    async def get_extensions(self) -> list:
        r = await self._request_with_retry("get", "/extensions")
        return r.json()

    async def get_features(self) -> dict:
        r = await self._request_with_retry("get", "/features")
        return r.json()

    async def get_model_types(self) -> list:
        r = await self._request_with_retry("get", "/models")
        return r.json()

    async def get_view_metadata(self, folder: str, filename: str) -> dict:
        r = await self._request_with_retry(
            "get", f"/view_metadata/{folder}", params={"filename": filename}
        )
        return r.json()

    async def get_prompt_status(self) -> dict:
        r = await self._request_with_retry("get", "/prompt")
        return r.json()

    async def clear_queue(
        self, clear_running: bool = False, clear_pending: bool = False
    ) -> None:
        data: dict[str, list[str]] = {"clear": []}
        if clear_running:
            data["clear"].append("running")
        if clear_pending:
            data["clear"].append("pending")
        await self._request_with_retry("post", "/queue", json=data)

    async def upload_mask(
        self, data: bytes, filename: str, subfolder: str = ""
    ) -> dict:
        files = {"mask": (filename, data, "image/png")}
        form_data: dict[str, str] = {}
        if subfolder:
            form_data["subfolder"] = subfolder
        r = await self._request_with_retry(
            "post", "/upload/mask", files=files, data=form_data
        )
        return r.json()
