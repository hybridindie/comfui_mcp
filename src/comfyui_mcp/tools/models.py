"""Model search and download tools backed by ComfyUI-Model-Manager."""

from __future__ import annotations

import json
from typing import Any

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
) -> list[dict[str, Any]]:
    """Search CivitAI for models."""
    params: dict[str, str | int] = {"query": query, "limit": limit}
    if model_type:
        params["types"] = model_type
    params["sort"] = "Most Downloaded"

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient() as http:
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


async def _search_huggingface(
    query: str,
    model_type: str,
    limit: int,
    token: str,
) -> list[dict[str, Any]]:
    """Search HuggingFace for models."""
    params: dict[str, str | int] = {"search": query, "limit": limit}
    if model_type:
        params["pipeline_tag"] = model_type

    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as http:
        r = await http.get(_HF_API, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        models = r.json()

    results: list[dict[str, Any]] = []
    for model in models:
        model_id = model.get("id", "")

        # Fetch file details to find the primary model file
        detail_url = f"{_HF_API}/{model_id}"
        try:
            async with httpx.AsyncClient() as http:
                dr = await http.get(detail_url, headers=headers, timeout=30)
                dr.raise_for_status()
                detail = dr.json()
        except httpx.HTTPError:
            detail = {}

        # Find the largest model file
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

        results.append(
            {
                "name": model_id,
                "type": model.get("pipeline_tag", ""),
                "url": download_url,
                "filename": model_file or "",
                "size_mb": round(model_size / (1024 * 1024), 1) if model_size else 0,
                "downloads": model.get("downloads", 0),
                "likes": model.get("likes", 0),
                "source": "huggingface",
            }
        )
    return results


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

        if source not in ("civitai", "huggingface"):
            raise ValueError("source must be 'civitai' or 'huggingface'")

        cap = min(limit, search_settings.max_search_results)

        audit.log(
            tool="search_models",
            action="searching",
            extra={"query": query, "source": source, "model_type": model_type},
        )

        if source == "civitai":
            results = await _search_civitai(query, model_type, cap, search_settings.civitai_api_key)
        else:
            results = await _search_huggingface(
                query, model_type, cap, search_settings.huggingface_token
            )

        audit.log(
            tool="search_models",
            action="searched",
            extra={"source": source, "result_count": len(results)},
        )

        return json.dumps({"results": results, "source": source, "query": query})

    tool_fns["search_models"] = search_models

    return tool_fns
