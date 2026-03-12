"""Model search and download tools backed by ComfyUI-Model-Manager."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.config import ModelSearchSettings
from comfyui_mcp.model_manager import ModelManagerDetector
from comfyui_mcp.security.download_validator import DownloadValidator
from comfyui_mcp.security.rate_limit import RateLimiter
from comfyui_mcp.security.sanitizer import PathSanitizer

_HF_API = "https://huggingface.co/api/models"
_CIVITAI_API = "https://civitai.com/api/v1/models"

# Extensions we look for when finding the primary model file in HuggingFace repos
_MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}


async def _search_civitai(
    query: str,
    model_type: str,
    limit: int,
    api_key: str,
    http: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Search CivitAI for models."""
    params: dict[str, str | int] = {"query": query, "limit": limit}
    if model_type:
        params["types"] = model_type
    params["sort"] = "Most Downloaded"

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    r = await http.get(_CIVITAI_API, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    results: list[dict[str, Any]] = []
    for item in data.get("items", []):
        versions = item.get("modelVersions", [])
        if not versions:
            continue
        latest = versions[0]
        files = latest.get("files", [])
        size_kb = files[0].get("sizeKB", 0) if files else 0
        filename = files[0].get("name", "") if files else ""
        results.append(
            {
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "url": latest.get("downloadUrl", ""),
                "filename": filename,
                "size_mb": round(size_kb / 1024, 1),
                "downloads": item.get("stats", {}).get("downloadCount", 0),
                "rating": item.get("stats", {}).get("rating", 0),
                "source": "civitai",
            }
        )
    return results


async def _fetch_hf_model_detail(
    http: httpx.AsyncClient,
    model: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    """Fetch detail for a single HuggingFace model."""
    model_id = model.get("id", "")
    detail_url = f"{_HF_API}/{model_id}"
    try:
        dr = await http.get(detail_url, headers=headers, timeout=30)
        dr.raise_for_status()
        detail = dr.json()
    except httpx.HTTPError:
        detail = {}

    siblings = detail.get("siblings", [])
    model_file = None
    model_size = 0
    for sib in siblings:
        fname = sib.get("rfilename", "")
        ext = "." + fname.rsplit(".", 1)[-1] if "." in fname else ""
        if ext.lower() in _MODEL_EXTENSIONS:
            size = sib.get("size", 0)
            if size > model_size:
                model_size = size
                model_file = fname

    download_url = ""
    if model_file:
        download_url = f"https://huggingface.co/{model_id}/resolve/main/{model_file}"

    return {
        "name": model_id,
        "type": model.get("pipeline_tag", ""),
        "url": download_url,
        "filename": model_file or "",
        "size_mb": round(model_size / (1024 * 1024), 1) if model_size else 0,
        "downloads": model.get("downloads", 0),
        "likes": model.get("likes", 0),
        "source": "huggingface",
    }


async def _search_huggingface(
    query: str,
    model_type: str,
    limit: int,
    token: str,
    http: httpx.AsyncClient,
) -> list[dict[str, Any]]:
    """Search HuggingFace for models with concurrent detail fetches."""
    params: dict[str, str | int] = {"search": query, "limit": limit}
    if model_type:
        params["pipeline_tag"] = model_type

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    r = await http.get(_HF_API, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    models = r.json()

    results = await asyncio.gather(*[_fetch_hf_model_detail(http, m, headers) for m in models])
    return list(results)


def register_model_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    read_limiter: RateLimiter,
    file_limiter: RateLimiter,
    sanitizer: PathSanitizer,
    detector: ModelManagerDetector,
    validator: DownloadValidator,
    search_settings: ModelSearchSettings,
    search_http: httpx.AsyncClient,
) -> dict[str, Any]:
    """Register model search and download tools."""
    tool_fns: dict[str, Any] = {}

    @mcp.tool()
    async def search_models(
        query: str,
        source: str = "civitai",
        model_type: str = "",
        limit: int = 5,
    ) -> str:
        """Search for models on HuggingFace or CivitAI.

        Args:
            query: Search query (model name, style, etc.)
            source: Where to search — "civitai" (default) or "huggingface"
            model_type: Filter by type. CivitAI: Checkpoint, LORA, TextualInversion, etc.
                        HuggingFace: text-to-image, etc.
            limit: Maximum results to return (default: 5)

        Returns:
            JSON with search results including name, download URL, size, and stats.
            Use download_model with the URL to install a model.
        """
        read_limiter.check("search_models")

        # Input validation
        stripped_query = query.strip()
        if not stripped_query:
            raise ValueError("query must not be empty")
        if len(stripped_query) > 200:
            raise ValueError("query must not exceed 200 characters")
        if model_type and len(model_type) > 100:
            raise ValueError("model_type must not exceed 100 characters")

        if source not in ("civitai", "huggingface"):
            raise ValueError("source must be 'civitai' or 'huggingface'")

        cap = max(1, min(limit, search_settings.max_search_results))

        audit.log(
            tool="search_models",
            action="searching",
            extra={"query": stripped_query, "source": source, "model_type": model_type},
        )

        if source == "civitai":
            results = await _search_civitai(
                stripped_query, model_type, cap, search_settings.civitai_api_key, search_http
            )
        else:
            results = await _search_huggingface(
                stripped_query, model_type, cap, search_settings.huggingface_token, search_http
            )

        audit.log(
            tool="search_models",
            action="searched",
            extra={"source": source, "result_count": len(results)},
        )

        return json.dumps({"results": results, "source": source, "query": stripped_query})

    tool_fns["search_models"] = search_models

    @mcp.tool()
    async def download_model(
        url: str,
        folder: str,
        filename: str = "",
    ) -> str:
        """Download a model from HuggingFace or CivitAI via ComfyUI-Model-Manager.

        Args:
            url: Direct download URL (must be from an allowed domain)
            folder: Target model folder (e.g. "checkpoints", "loras", "vae")
            filename: Filename to save as (optional — inferred from URL if empty)

        Returns:
            JSON with download task status. Use get_download_tasks to check progress.
        """
        file_limiter.check("download_model")

        # Validate URL domain and path pattern
        validator.validate_url(url)

        # Validate folder
        sanitizer.validate_path_segment(folder, label="folder")
        await detector.validate_folder(folder)

        # Infer filename from URL if not provided
        if not filename:
            path = urlparse(url).path
            filename = path.rsplit("/", 1)[-1] if "/" in path else ""
            if not filename:
                raise ValueError("Could not infer filename from URL. Please provide a filename.")

        # Validate extension and filename
        validator.validate_extension(filename)
        sanitizer.validate_filename(filename)

        # Infer download platform from URL
        hostname = (urlparse(url).hostname or "").lower()
        if "civitai" in hostname:
            platform = "civitai"
        elif "huggingface" in hostname:
            platform = "huggingface"
        else:
            platform = "other"

        audit.log(
            tool="download_model",
            action="downloading",
            extra={"url": url, "folder": folder, "filename": filename, "platform": platform},
        )

        result = await client.create_download_task(
            model_type=folder,
            path_index=0,
            fullname=filename,
            download_platform=platform,
            download_url=url,
            size_bytes=0,
        )

        audit.log(
            tool="download_model",
            action="download_started",
            extra={"result": result, "folder": folder, "filename": filename},
        )

        return json.dumps(result)

    tool_fns["download_model"] = download_model

    @mcp.tool()
    async def get_download_tasks() -> str:
        """Check the status of active model downloads.

        Returns:
            JSON with list of download tasks including progress, speed, and status.
        """
        read_limiter.check("get_download_tasks")
        await detector.get_folders()  # Ensure Model Manager is available

        audit.log(tool="get_download_tasks", action="checking")

        tasks = await client.get_download_tasks()

        audit.log(
            tool="get_download_tasks",
            action="checked",
            extra={"task_count": len(tasks)},
        )

        return json.dumps({"tasks": tasks})

    tool_fns["get_download_tasks"] = get_download_tasks

    @mcp.tool()
    async def cancel_download(task_id: str) -> str:
        """Cancel and remove a model download task.

        Args:
            task_id: ID of the download task to cancel
        """
        file_limiter.check("cancel_download")
        await detector.get_folders()  # Ensure Model Manager is available

        audit.log(
            tool="cancel_download",
            action="cancelling",
            extra={"task_id": task_id},
        )

        result = await client.delete_download_task(task_id)

        success = bool(result.get("success", True)) if isinstance(result, dict) else True

        audit.log(
            tool="cancel_download",
            action="cancelled",
            extra={"task_id": task_id, "result": result, "success": success},
        )

        return json.dumps({"success": success, "task_id": task_id, "result": result})

    tool_fns["cancel_download"] = cancel_download

    return tool_fns
