# Model Search & Download Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tools to search HuggingFace/CivitAI for models and download them via ComfyUI-Model-Manager, with proactive missing-model detection during workflow submission.

**Architecture:** MCP server acts as thin orchestration layer. Search calls go to external APIs (HuggingFace/CivitAI) via httpx. Downloads are forwarded to ComfyUI-Model-Manager's REST API. A lazy detector gates all model tools on Model Manager availability. Proactive model checking happens during workflow inspection.

**Tech Stack:** Python 3.12, httpx (async HTTP), pydantic (config), FastMCP (tool registration), respx (test mocking)

**Spec:** `docs/superpowers/specs/2026-03-11-model-download-design.md`

---

## Chunk 1: Configuration & Client

### Task 1: Add config settings for model search and download

**Files:**
- Modify: `src/comfyui_mcp/config.py:65-70` (SecuritySettings), `src/comfyui_mcp/config.py:103-108` (Settings), `src/comfyui_mcp/config.py:111-133` (_apply_env_overrides)
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config fields**

```python
# In tests/test_config.py — add imports at top of file:
# from comfyui_mcp.config import ModelSearchSettings
# (SecuritySettings and _apply_env_overrides should already be imported)

class TestModelSearchSettings:
    def test_default_values(self):
        s = ModelSearchSettings()
        assert s.huggingface_token == ""
        assert s.civitai_api_key == ""
        assert s.max_search_results == 10

    def test_custom_values(self):
        s = ModelSearchSettings(huggingface_token="hf_xxx", civitai_api_key="civ_yyy", max_search_results=5)
        assert s.huggingface_token == "hf_xxx"
        assert s.civitai_api_key == "civ_yyy"
        assert s.max_search_results == 5


class TestDownloadSecuritySettings:
    def test_default_allowed_download_domains(self):
        s = SecuritySettings()
        assert "huggingface.co" in s.allowed_download_domains
        assert "civitai.com" in s.allowed_download_domains

    def test_default_allowed_model_extensions(self):
        s = SecuritySettings()
        assert ".safetensors" in s.allowed_model_extensions
        assert ".ckpt" in s.allowed_model_extensions
        assert ".pt" in s.allowed_model_extensions
        assert ".pth" in s.allowed_model_extensions
        assert ".bin" in s.allowed_model_extensions

    def test_custom_download_domains(self):
        s = SecuritySettings(allowed_download_domains=["example.com"])
        assert s.allowed_download_domains == ["example.com"]


class TestModelSearchEnvOverrides:
    def test_huggingface_token_env(self, monkeypatch):
        monkeypatch.setenv("COMFYUI_HUGGINGFACE_TOKEN", "hf_test123")
        data = _apply_env_overrides({})
        assert data["model_search"]["huggingface_token"] == "hf_test123"

    def test_civitai_api_key_env(self, monkeypatch):
        monkeypatch.setenv("COMFYUI_CIVITAI_API_KEY", "civ_test456")
        data = _apply_env_overrides({})
        assert data["model_search"]["civitai_api_key"] == "civ_test456"

    def test_max_search_results_env(self, monkeypatch):
        monkeypatch.setenv("COMFYUI_MAX_SEARCH_RESULTS", "20")
        data = _apply_env_overrides({})
        assert data["model_search"]["max_search_results"] == 20

    def test_allowed_download_domains_env(self, monkeypatch):
        monkeypatch.setenv("COMFYUI_ALLOWED_DOWNLOAD_DOMAINS", "example.com,other.com")
        data = _apply_env_overrides({})
        assert data["security"]["allowed_download_domains"] == ["example.com", "other.com"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v -k "ModelSearch or DownloadSecurity or ModelSearchEnv"`
Expected: FAIL — `ModelSearchSettings` not defined, fields don't exist

- [ ] **Step 3: Implement config changes**

In `src/comfyui_mcp/config.py`, add:

```python
# After line 45 (_DEFAULT_ALLOWED_EXTENSIONS)
_DEFAULT_ALLOWED_DOWNLOAD_DOMAINS = ["huggingface.co", "civitai.com"]
_DEFAULT_ALLOWED_MODEL_EXTENSIONS = [".safetensors", ".ckpt", ".pt", ".pth", ".bin"]
```

```python
# New class after SecuritySettings (after line 80)
class ModelSearchSettings(BaseModel):
    huggingface_token: str = ""
    civitai_api_key: str = ""
    max_search_results: int = 10
```

Add to `SecuritySettings` (lines 65-70):
```python
    allowed_download_domains: list[str] = list(_DEFAULT_ALLOWED_DOWNLOAD_DOMAINS)
    allowed_model_extensions: list[str] = list(_DEFAULT_ALLOWED_MODEL_EXTENSIONS)
```

Add to `Settings` (lines 103-108):
```python
    model_search: ModelSearchSettings = ModelSearchSettings()
```

Add to `_apply_env_overrides` env_map (lines 113-120):
```python
        "COMFYUI_HUGGINGFACE_TOKEN": ("model_search", "huggingface_token"),
        "COMFYUI_CIVITAI_API_KEY": ("model_search", "civitai_api_key"),
        "COMFYUI_MAX_SEARCH_RESULTS": ("model_search", "max_search_results"),
        "COMFYUI_ALLOWED_DOWNLOAD_DOMAINS": ("security", "allowed_download_domains"),
```

Update the type-conversion logic in `_apply_env_overrides` (around line 127) to handle `max_search_results` as int and `allowed_download_domains` as comma-separated list:
```python
            if key in ("timeout_connect", "timeout_read", "max_search_results"):
                data[section][key] = int(value)
            elif key == "tls_verify":
                data[section][key] = value.lower() in ("true", "1", "yes")
            elif key == "allowed_download_domains":
                data[section][key] = [d.strip() for d in value.split(",") if d.strip()]
            else:
                data[section][key] = value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v -k "ModelSearch or DownloadSecurity or ModelSearchEnv"`
Expected: PASS

- [ ] **Step 5: Run full test suite, lint, and type check**

Run: `uv run pytest -v && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/config.py tests/test_config.py
git commit -m "feat(config): add model search and download settings"
```

---

### Task 2: Add Model Manager client methods

**Files:**
- Modify: `src/comfyui_mcp/client.py:160` (append new methods)
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing tests for new client methods**

```python
# Add to tests/test_client.py

class TestModelManagerClient:
    @respx.mock
    async def test_check_model_manager_available(self, client):
        respx.get("http://test-comfyui:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        result = await client.check_model_manager()
        assert result is True

    @respx.mock
    async def test_check_model_manager_not_available(self, client):
        respx.get("http://test-comfyui:8188/model-manager/models").mock(
            return_value=httpx.Response(404)
        )
        result = await client.check_model_manager()
        assert result is False

    @respx.mock
    async def test_check_model_manager_connection_error(self):
        # Use max_retries=1 to avoid slow retry backoff in tests
        fast_client = ComfyUIClient(base_url="http://test-comfyui:8188", max_retries=1)
        respx.get("http://test-comfyui:8188/model-manager/models").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await fast_client.check_model_manager()
        assert result is False

    @respx.mock
    async def test_get_model_manager_folders(self, client):
        respx.get("http://test-comfyui:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        result = await client.get_model_manager_folders()
        assert result == ["checkpoints", "loras", "vae"]

    @respx.mock
    async def test_create_download_task(self, client):
        respx.post("http://test-comfyui:8188/model-manager/model").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"taskId": "task-1"}})
        )
        result = await client.create_download_task(
            model_type="checkpoints",
            path_index=0,
            fullname="model.safetensors",
            download_platform="huggingface",
            download_url="https://huggingface.co/org/repo/resolve/main/model.safetensors",
            size_bytes=1000000,
        )
        assert result["success"] is True

    @respx.mock
    async def test_get_download_tasks(self, client):
        respx.get("http://test-comfyui:8188/model-manager/download/task").mock(
            return_value=httpx.Response(200, json=[
                {"taskId": "t1", "status": "doing", "progress": 50}
            ])
        )
        result = await client.get_download_tasks()
        assert len(result) == 1
        assert result[0]["taskId"] == "t1"

    @respx.mock
    async def test_delete_download_task(self, client):
        respx.delete("http://test-comfyui:8188/model-manager/download/task-1").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        result = await client.delete_download_task("task-1")
        assert result["success"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestModelManagerClient -v`
Expected: FAIL — methods not defined

- [ ] **Step 3: Implement client methods**

Append to `src/comfyui_mcp/client.py` (after line 159):

```python
    # --- Model Manager endpoints ---

    async def check_model_manager(self) -> bool:
        """Check if ComfyUI-Model-Manager is installed.

        Returns True if the Model Manager API is reachable, False otherwise.
        """
        try:
            await self._request("get", "/model-manager/models")
            return True
        except (httpx.HTTPStatusError, httpx.RequestError):
            return False

    async def get_model_manager_folders(self) -> list[str]:
        """GET /model-manager/models — list available model folder types."""
        r = await self._request("get", "/model-manager/models")
        return r.json()

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
        }
        if preview_url:
            form_data["previewFile"] = preview_url
        if description:
            form_data["description"] = description
        r = await self._request("post", "/model-manager/model", data=form_data)
        return r.json()

    async def get_download_tasks(self) -> list[dict]:
        """GET /model-manager/download/task — list download tasks with progress."""
        r = await self._request("get", "/model-manager/download/task")
        return r.json()

    async def delete_download_task(self, task_id: str) -> dict:
        """DELETE /model-manager/download/{task_id} — cancel and remove a download."""
        r = await self._request("delete", f"/model-manager/download/{task_id}")
        return r.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestModelManagerClient -v`
Expected: PASS

- [ ] **Step 5: Run full test suite, lint, and type check**

Run: `uv run pytest -v && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/client.py tests/test_client.py
git commit -m "feat(client): add Model Manager client methods"
```

---

## Chunk 2: Model Manager Detection & URL Validation

### Task 3: Create ModelManagerDetector with lazy init

**Files:**
- Create: `src/comfyui_mcp/model_manager.py`
- Test: `tests/test_model_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_model_manager.py
import httpx
import pytest
import respx

from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.model_manager import ModelManagerDetector, ModelManagerUnavailableError


@pytest.fixture
def client():
    return ComfyUIClient(base_url="http://test:8188")


class TestModelManagerDetector:
    @respx.mock
    async def test_detect_available(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        detector = ModelManagerDetector(client)
        folders = await detector.get_folders()
        assert "checkpoints" in folders
        assert "loras" in folders

    @respx.mock
    async def test_detect_unavailable(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(404)
        )
        detector = ModelManagerDetector(client)
        with pytest.raises(ModelManagerUnavailableError, match="not detected"):
            await detector.get_folders()

    @respx.mock
    async def test_caches_result(self, client):
        route = respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        detector = ModelManagerDetector(client)
        await detector.get_folders()
        await detector.get_folders()
        assert route.call_count == 1

    @respx.mock
    async def test_is_available_true(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        detector = ModelManagerDetector(client)
        assert await detector.is_available() is True

    @respx.mock
    async def test_is_available_false(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(404)
        )
        detector = ModelManagerDetector(client)
        assert await detector.is_available() is False

    @respx.mock
    async def test_validate_folder_known(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras"])
        )
        detector = ModelManagerDetector(client)
        await detector.validate_folder("checkpoints")  # Should not raise

    @respx.mock
    async def test_validate_folder_unknown(self, client):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras"])
        )
        detector = ModelManagerDetector(client)
        with pytest.raises(ValueError, match="not a valid model folder"):
            await detector.validate_folder("invalid_folder")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_model_manager.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement ModelManagerDetector**

Create `src/comfyui_mcp/model_manager.py`:

```python
"""Lazy detector for ComfyUI-Model-Manager availability."""

from __future__ import annotations

import asyncio

import httpx

from comfyui_mcp.client import ComfyUIClient


class ModelManagerUnavailableError(Exception):
    """Raised when Model Manager is not installed or unreachable."""


class ModelManagerDetector:
    """Lazy-init detector that probes Model Manager on first use and caches the result.

    Uses asyncio.Lock to prevent concurrent probes from racing.
    Calls GET /model-manager/models once — the response both confirms availability
    and provides the folder list in a single round-trip.
    """

    _INSTALL_URL = "https://github.com/hayden-fr/ComfyUI-Model-Manager"

    def __init__(self, client: ComfyUIClient) -> None:
        self._client = client
        self._folders: list[str] | None = None
        self._checked = False
        self._available = False
        self._lock = asyncio.Lock()

    async def _probe(self) -> None:
        """Probe Model Manager once and cache the result."""
        async with self._lock:
            if self._checked:
                return
            self._checked = True
            try:
                self._folders = await self._client.get_model_manager_folders()
                self._available = True
            except (httpx.HTTPStatusError, httpx.RequestError):
                self._available = False

    async def is_available(self) -> bool:
        """Check if Model Manager is installed. Caches the result."""
        await self._probe()
        return self._available

    async def get_folders(self) -> list[str]:
        """Return cached folder list, or raise if Model Manager is unavailable."""
        await self._probe()
        if not self._available or self._folders is None:
            raise ModelManagerUnavailableError(
                "ComfyUI-Model-Manager not detected. "
                f"Install it from {self._INSTALL_URL}"
            )
        return self._folders

    async def validate_folder(self, folder: str) -> None:
        """Raise ValueError if folder is not in Model Manager's known folders."""
        folders = await self.get_folders()
        if folder not in folders:
            raise ValueError(
                f"'{folder}' is not a valid model folder. "
                f"Available: {', '.join(sorted(folders))}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_model_manager.py -v`
Expected: PASS

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/model_manager.py tests/test_model_manager.py
git commit -m "feat: add ModelManagerDetector with lazy initialization"
```

---

### Task 4: Add URL validation for download domains

**Files:**
- Create: `src/comfyui_mcp/security/download_validator.py`
- Test: `tests/test_download_validator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_download_validator.py
import pytest

from comfyui_mcp.security.download_validator import DownloadValidator, DownloadValidationError


@pytest.fixture
def validator():
    return DownloadValidator(
        allowed_domains=["huggingface.co", "civitai.com"],
        allowed_extensions=[".safetensors", ".ckpt", ".pt", ".pth", ".bin"],
    )


class TestDomainValidation:
    def test_huggingface_resolve_url(self, validator):
        url = "https://huggingface.co/stabilityai/sdxl/resolve/main/model.safetensors"
        validator.validate_url(url)  # Should not raise

    def test_civitai_download_url(self, validator):
        url = "https://civitai.com/api/download/models/12345"
        validator.validate_url(url)  # Should not raise

    def test_blocked_domain(self, validator):
        url = "https://evil.com/model.safetensors"
        with pytest.raises(DownloadValidationError, match="not in allowed domains"):
            validator.validate_url(url)

    def test_no_scheme(self, validator):
        with pytest.raises(DownloadValidationError, match="must use https"):
            validator.validate_url("ftp://huggingface.co/model.safetensors")

    def test_http_rejected(self, validator):
        with pytest.raises(DownloadValidationError, match="must use https"):
            validator.validate_url("http://huggingface.co/model.safetensors")

    def test_custom_domain(self):
        v = DownloadValidator(
            allowed_domains=["models.example.com"],
            allowed_extensions=[".safetensors"],
        )
        v.validate_url("https://models.example.com/my-model.safetensors")


class TestExtensionValidation:
    def test_safetensors(self, validator):
        validator.validate_extension("model.safetensors")

    def test_ckpt(self, validator):
        validator.validate_extension("model.ckpt")

    def test_invalid_extension(self, validator):
        with pytest.raises(DownloadValidationError, match="extension"):
            validator.validate_extension("model.exe")

    def test_no_extension(self, validator):
        with pytest.raises(DownloadValidationError, match="extension"):
            validator.validate_extension("model")


class TestUrlPathValidation:
    def test_hf_resolve_path(self, validator):
        url = "https://huggingface.co/org/repo/resolve/main/model.safetensors"
        validator.validate_url(url)

    def test_civitai_api_path(self, validator):
        url = "https://civitai.com/api/download/models/12345"
        validator.validate_url(url)

    def test_hf_non_resolve_path_rejected(self, validator):
        url = "https://huggingface.co/some/random/path"
        with pytest.raises(DownloadValidationError, match="URL path"):
            validator.validate_url(url)

    def test_civitai_non_api_path_rejected(self, validator):
        url = "https://civitai.com/models/12345"
        with pytest.raises(DownloadValidationError, match="URL path"):
            validator.validate_url(url)

    def test_custom_domain_no_path_validation(self):
        """Custom domains beyond HF/CivitAI don't have path pattern checks."""
        v = DownloadValidator(
            allowed_domains=["models.example.com"],
            allowed_extensions=[".safetensors"],
        )
        v.validate_url("https://models.example.com/any/path/model.safetensors")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_download_validator.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement DownloadValidator**

Create `src/comfyui_mcp/security/download_validator.py`:

```python
"""URL and extension validation for model downloads."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import urlparse


class DownloadValidationError(Exception):
    """Raised when a download URL or filename fails validation."""


# Known direct-download path patterns for allowlisted domains.
# URLs matching an allowlisted domain must also match one of these patterns
# (if defined for that domain). This mitigates open-redirect risks.
_DOMAIN_PATH_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "huggingface.co": [
        re.compile(r"^/[^/]+/[^/]+/resolve/"),  # /{org}/{repo}/resolve/{ref}/...
    ],
    "civitai.com": [
        re.compile(r"^/api/download/"),  # /api/download/models/{id}
    ],
}


class DownloadValidator:
    """Validates download URLs against domain and extension allowlists."""

    def __init__(
        self,
        allowed_domains: list[str],
        allowed_extensions: list[str],
    ) -> None:
        self._allowed_domains = [d.lower() for d in allowed_domains]
        self._allowed_extensions = {ext.lower() for ext in allowed_extensions}

    def validate_url(self, url: str) -> None:
        """Validate that a URL is from an allowed domain with a valid path pattern.

        Raises DownloadValidationError if validation fails.
        """
        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise DownloadValidationError(
                f"Download URL must use https, got {parsed.scheme!r}"
            )

        hostname = (parsed.hostname or "").lower()
        if not self._is_allowed_domain(hostname):
            raise DownloadValidationError(
                f"Domain {hostname!r} not in allowed domains: "
                f"{', '.join(self._allowed_domains)}"
            )

        # Check path patterns for known domains
        self._validate_path_pattern(hostname, parsed.path)

    def _is_allowed_domain(self, hostname: str) -> bool:
        """Check if hostname matches or is a subdomain of an allowed domain."""
        for domain in self._allowed_domains:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
        return False

    def _validate_path_pattern(self, hostname: str, path: str) -> None:
        """Validate URL path against known patterns for specific domains."""
        # Find the base domain that matched
        matched_domain = None
        for domain in self._allowed_domains:
            if hostname == domain or hostname.endswith(f".{domain}"):
                matched_domain = domain
                break

        if matched_domain is None:
            return  # Should not happen — validate_url checks domain first

        patterns = _DOMAIN_PATH_PATTERNS.get(matched_domain)
        if patterns is None:
            return  # No path restrictions for custom domains

        if not any(p.search(path) for p in patterns):
            raise DownloadValidationError(
                f"URL path {path!r} does not match expected download patterns "
                f"for {matched_domain}"
            )

    def validate_extension(self, filename: str) -> None:
        """Validate that a filename has an allowed model extension.

        Raises DownloadValidationError if extension is not allowed.
        """
        suffix = PurePosixPath(filename).suffix.lower()
        if not suffix or suffix not in self._allowed_extensions:
            raise DownloadValidationError(
                f"File extension {suffix!r} not allowed. "
                f"Allowed: {sorted(self._allowed_extensions)}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_download_validator.py -v`
Expected: PASS

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/security/download_validator.py tests/test_download_validator.py
git commit -m "feat(security): add URL and extension validation for model downloads"
```

---

## Chunk 3: Model Tools

### Task 5: Create model tools — search_models

**Files:**
- Create: `src/comfyui_mcp/tools/models.py`
- Test: `tests/test_tools_models.py`

- [ ] **Step 1: Write failing tests for search_models**

```python
# tests/test_tools_models.py
import json

import httpx
import pytest
import respx
from mcp.server.fastmcp import FastMCP

from comfyui_mcp.audit import AuditLogger
from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.config import ModelSearchSettings, SecuritySettings
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
            return_value=httpx.Response(200, json={
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
                                "files": [{"sizeKB": 2048000, "name": "epicrealism_v5.safetensors"}],
                            }
                        ],
                    }
                ],
                "metadata": {"totalItems": 1},
            })
        )
        result = await registered_tools["search_models"](
            query="epic realism", source="civitai"
        )
        parsed = json.loads(result)
        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["name"] == "Epic Realism"

    @respx.mock
    async def test_search_huggingface(self, registered_tools):
        # First call: search
        respx.get("https://huggingface.co/api/models").mock(
            return_value=httpx.Response(200, json=[
                {
                    "id": "stabilityai/sdxl",
                    "modelId": "stabilityai/sdxl",
                    "downloads": 1000000,
                    "pipeline_tag": "text-to-image",
                    "tags": ["diffusers", "safetensors"],
                    "likes": 500,
                }
            ])
        )
        # Second call: file details
        respx.get("https://huggingface.co/api/models/stabilityai/sdxl").mock(
            return_value=httpx.Response(200, json={
                "id": "stabilityai/sdxl",
                "siblings": [
                    {"rfilename": "model.safetensors", "size": 6800000000},
                    {"rfilename": "README.md", "size": 1000},
                ],
            })
        )
        result = await registered_tools["search_models"](
            query="sdxl", source="huggingface"
        )
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_models.py::TestSearchModels -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement search_models in tools/models.py**

Create `src/comfyui_mcp/tools/models.py`:

```python
"""Model search and download tools backed by ComfyUI-Model-Manager."""

from __future__ import annotations

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
        results.append({
            "name": item.get("name", ""),
            "type": item.get("type", ""),
            "url": latest.get("downloadUrl", ""),
            "filename": filename,
            "size_mb": round(size_kb / 1024, 1),
            "downloads": item.get("stats", {}).get("downloadCount", 0),
            "rating": item.get("stats", {}).get("rating", 0),
            "source": "civitai",
        })
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

        results.append({
            "name": model_id,
            "type": model.get("pipeline_tag", ""),
            "url": download_url,
            "filename": model_file or "",
            "size_mb": round(model_size / (1024 * 1024), 1) if model_size else 0,
            "downloads": model.get("downloads", 0),
            "likes": model.get("likes", 0),
            "source": "huggingface",
        })
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
            results = await _search_civitai(
                query, model_type, cap, search_settings.civitai_api_key
            )
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
```

Note: We will add download_model, get_download_tasks, and cancel_download in the next task. Starting with search_models to keep the step small.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_models.py::TestSearchModels -v`
Expected: PASS

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/tools/models.py tests/test_tools_models.py
git commit -m "feat(tools): add search_models tool for HuggingFace and CivitAI"
```

---

### Task 6: Add download_model, get_download_tasks, cancel_download tools

**Files:**
- Modify: `src/comfyui_mcp/tools/models.py` (append tools after search_models)
- Modify: `tests/test_tools_models.py` (add test classes)

- [ ] **Step 1: Write failing tests for download tools**

Add to `tests/test_tools_models.py`:

```python
class TestDownloadModel:
    @respx.mock
    async def test_download_valid_model(self, registered_tools):
        # Mock Model Manager detection
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras", "vae"])
        )
        # Mock download task creation
        respx.post("http://test:8188/model-manager/model").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"taskId": "t-1"}})
        )
        result = await registered_tools["download_model"](
            url="https://civitai.com/api/download/models/12345",
            folder="checkpoints",
            filename="epicrealism.safetensors",
        )
        parsed = json.loads(result)
        assert parsed["success"] is True

    @respx.mock
    async def test_download_blocked_domain(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        with pytest.raises(Exception, match="not in allowed domains"):
            await registered_tools["download_model"](
                url="https://evil.com/model.safetensors",
                folder="checkpoints",
                filename="model.safetensors",
            )

    @respx.mock
    async def test_download_bad_extension(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        with pytest.raises(Exception, match="extension"):
            await registered_tools["download_model"](
                url="https://civitai.com/api/download/models/123",
                folder="checkpoints",
                filename="model.exe",
            )
        # Note: Model Manager mock is needed because folder validation runs
        # before extension validation per spec ordering

    @respx.mock
    async def test_download_invalid_folder(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints", "loras"])
        )
        with pytest.raises(ValueError, match="not a valid model folder"):
            await registered_tools["download_model"](
                url="https://civitai.com/api/download/models/123",
                folder="invalid_folder",
                filename="model.safetensors",
            )

    @respx.mock
    async def test_download_model_manager_unavailable(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(Exception, match="not detected"):
            await registered_tools["download_model"](
                url="https://civitai.com/api/download/models/123",
                folder="checkpoints",
                filename="model.safetensors",
            )

    @respx.mock
    async def test_download_infers_platform_huggingface(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        route = respx.post("http://test:8188/model-manager/model").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await registered_tools["download_model"](
            url="https://huggingface.co/org/repo/resolve/main/model.safetensors",
            folder="checkpoints",
            filename="model.safetensors",
        )
        body = route.calls[0].request.content.decode()
        assert "huggingface" in body


class TestGetDownloadTasks:
    @respx.mock
    async def test_get_tasks(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        respx.get("http://test:8188/model-manager/download/task").mock(
            return_value=httpx.Response(200, json=[
                {"taskId": "t1", "status": "doing", "progress": 75, "totalSize": 1000, "downloadedSize": 750}
            ])
        )
        result = await registered_tools["get_download_tasks"]()
        parsed = json.loads(result)
        assert len(parsed["tasks"]) == 1


class TestCancelDownload:
    @respx.mock
    async def test_cancel_task(self, registered_tools):
        respx.get("http://test:8188/model-manager/models").mock(
            return_value=httpx.Response(200, json=["checkpoints"])
        )
        respx.delete("http://test:8188/model-manager/download/task-1").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        result = await registered_tools["cancel_download"](task_id="task-1")
        assert "cancelled" in result.lower() or "canceled" in result.lower() or "success" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tools_models.py -v -k "Download or Cancel"`
Expected: FAIL — tools not registered

- [ ] **Step 3: Implement download tools**

Add to `src/comfyui_mcp/tools/models.py` inside `register_model_tools()`, after the `search_models` registration (before the final `return tool_fns`):

```python
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

        # Validate folder: safety first, then business logic (per spec)
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

        audit.log(
            tool="cancel_download",
            action="cancelled",
            extra={"task_id": task_id, "result": result},
        )

        return json.dumps({"success": True, "task_id": task_id, "message": "Download cancelled"})

    tool_fns["cancel_download"] = cancel_download
```

Note: `from urllib.parse import urlparse` is already in the module-level imports shown in Task 5 Step 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_models.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite, lint, and type check**

Run: `uv run pytest -v && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/tools/models.py tests/test_tools_models.py
git commit -m "feat(tools): add download_model, get_download_tasks, cancel_download tools"
```

---

## Chunk 4: Server Wiring & Proactive Model Check

### Task 7: Wire model tools into server.py

**Files:**
- Modify: `src/comfyui_mcp/server.py`

- [ ] **Step 1: Write failing test**

```python
# Add to an appropriate test file, e.g. tests/test_server.py or tests/test_tools_models.py

class TestServerWiring:
    def test_model_tools_registered(self):
        """Verify that _register_all_tools accepts the new parameters."""
        # This is an integration check — if model tools are properly wired,
        # the import and registration should not error.
        from comfyui_mcp.server import _build_server
        from comfyui_mcp.config import Settings
        # Build with default settings (no real ComfyUI connection)
        server, settings = _build_server(settings=Settings())
        # Server should build without error — model tools are registered
        # but gated behind lazy detector
        assert server is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools_models.py::TestServerWiring -v` (or wherever you placed it)
Expected: FAIL — `_register_all_tools` doesn't accept the new params yet

- [ ] **Step 3: Wire model tools into server.py**

Modify `src/comfyui_mcp/server.py`:

Add imports at the top:
```python
from comfyui_mcp.model_manager import ModelManagerDetector
from comfyui_mcp.security.download_validator import DownloadValidator
from comfyui_mcp.security.model_checker import ModelChecker
from comfyui_mcp.tools.models import register_model_tools
```

`_register_all_tools` signature stays the same (no `settings` param). Instead, create
components in `_build_server()` following the existing factory pattern, and pass them as
parameters.

Add to `_build_server()`, after the existing component creation (after `rate_limiters`):
```python
    # Model tools dependencies — follow factory pattern
    detector = ModelManagerDetector(client)
    model_sanitizer = PathSanitizer(
        allowed_extensions=settings.security.allowed_model_extensions,
        max_size_mb=settings.security.max_upload_size_mb,
    )
    download_validator = DownloadValidator(
        allowed_domains=settings.security.allowed_download_domains,
        allowed_extensions=settings.security.allowed_model_extensions,
    )
    model_checker = ModelChecker()
```

Update `_register_all_tools` signature to accept the new components:
```python
def _register_all_tools(
    server: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    rate_limiters: dict[str, RateLimiter],
    inspector: WorkflowInspector,
    sanitizer: PathSanitizer,
    node_auditor: NodeAuditor,
    progress: WebSocketProgress,
    detector: ModelManagerDetector,
    model_sanitizer: PathSanitizer,
    download_validator: DownloadValidator,
    model_checker: ModelChecker,
    search_settings: ModelSearchSettings,
) -> None:
    """Register all MCP tool groups with their dependencies."""
    register_discovery_tools(server, client, audit, rate_limiters["read"], sanitizer, node_auditor)
    register_history_tools(server, client, audit, rate_limiters["read"])
    register_job_tools(
        server,
        client,
        audit,
        rate_limiters["workflow"],
        read_limiter=rate_limiters["read"],
        progress=progress,
    )
    register_file_tools(server, client, audit, rate_limiters["file"], sanitizer)
    register_generation_tools(
        server,
        client,
        audit,
        rate_limiters["generation"],
        inspector,
        read_limiter=rate_limiters["read"],
        progress=progress,
        model_checker=model_checker,
    )
    register_workflow_tools(server, client, audit, rate_limiters["read"], inspector)
    register_model_tools(
        mcp=server,
        client=client,
        audit=audit,
        read_limiter=rate_limiters["read"],
        file_limiter=rate_limiters["file"],
        sanitizer=model_sanitizer,
        detector=detector,
        validator=download_validator,
        search_settings=search_settings,
    )
```

Update `_build_server` call to `_register_all_tools`:
```python
    _register_all_tools(
        server,
        client,
        audit,
        rate_limiters,
        inspector,
        sanitizer,
        node_auditor,
        progress,
        detector,
        model_sanitizer,
        download_validator,
        model_checker,
        settings.model_search,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/server.py
git commit -m "feat(server): wire model tools with lazy Model Manager detection"
```

---

### Task 8: Add proactive model check to workflow inspector

**Files:**
- Create: `src/comfyui_mcp/security/model_checker.py`
- Test: `tests/test_model_checker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_model_checker.py
import httpx
import pytest
import respx

from comfyui_mcp.client import ComfyUIClient
from comfyui_mcp.security.model_checker import ModelChecker


@pytest.fixture
def client():
    return ComfyUIClient(base_url="http://test:8188")


@pytest.fixture
def checker():
    return ModelChecker()


class TestModelChecker:
    @respx.mock
    async def test_no_warnings_when_models_present(self, checker, client):
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["epicrealism_v5.safetensors", "sd_v15.safetensors"])
        )
        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "epicrealism_v5.safetensors"},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert warnings == []

    @respx.mock
    async def test_warns_missing_checkpoint(self, checker, client):
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["sd_v15.safetensors"])
        )
        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "missing_model.safetensors"},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert len(warnings) == 1
        assert "missing_model.safetensors" in warnings[0]
        assert "search_models" in warnings[0]

    @respx.mock
    async def test_warns_missing_lora(self, checker, client):
        respx.get("http://test:8188/models/loras").mock(
            return_value=httpx.Response(200, json=["detail_v1.safetensors"])
        )
        workflow = {
            "10": {
                "class_type": "LoraLoader",
                "inputs": {"lora_name": "missing_lora.safetensors", "model": ["4", 0]},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert len(warnings) == 1
        assert "missing_lora.safetensors" in warnings[0]

    @respx.mock
    async def test_multiple_missing_models(self, checker, client):
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("http://test:8188/models/loras").mock(
            return_value=httpx.Response(200, json=[])
        )
        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "missing.safetensors"},
            },
            "10": {
                "class_type": "LoraLoader",
                "inputs": {"lora_name": "missing_lora.safetensors", "model": ["4", 0]},
            },
        }
        warnings = await checker.check_models(workflow, client)
        assert len(warnings) == 2

    @respx.mock
    async def test_skips_unknown_node_types(self, checker, client):
        workflow = {
            "1": {
                "class_type": "SomeCustomNode",
                "inputs": {"value": "test"},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert warnings == []

    @respx.mock
    async def test_handles_api_error_gracefully(self, checker, client):
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(500)
        )
        workflow = {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"},
            }
        }
        # Should not raise — returns empty warnings on API failure
        warnings = await checker.check_models(workflow, client)
        assert warnings == []

    @respx.mock
    async def test_vae_loader(self, checker, client):
        respx.get("http://test:8188/models/vae").mock(
            return_value=httpx.Response(200, json=["vae-ft-mse.safetensors"])
        )
        workflow = {
            "5": {
                "class_type": "VAELoader",
                "inputs": {"vae_name": "missing_vae.safetensors"},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert len(warnings) == 1
        assert "missing_vae.safetensors" in warnings[0]

    @respx.mock
    async def test_controlnet_loader(self, checker, client):
        respx.get("http://test:8188/models/controlnet").mock(
            return_value=httpx.Response(200, json=[])
        )
        workflow = {
            "6": {
                "class_type": "ControlNetLoader",
                "inputs": {"control_net_name": "missing_cn.safetensors"},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert len(warnings) == 1

    @respx.mock
    async def test_upscale_model_loader(self, checker, client):
        respx.get("http://test:8188/models/upscale_models").mock(
            return_value=httpx.Response(200, json=[])
        )
        workflow = {
            "7": {
                "class_type": "UpscaleModelLoader",
                "inputs": {"model_name": "4x_ultrasharp.pt"},
            }
        }
        warnings = await checker.check_models(workflow, client)
        assert len(warnings) == 1

    @respx.mock
    async def test_input_is_reference_not_string(self, checker, client):
        """When input is a node reference like ['4', 0], skip it."""
        workflow = {
            "10": {
                "class_type": "LoraLoader",
                "inputs": {"lora_name": "detail.safetensors", "model": ["4", 0]},
            }
        }
        respx.get("http://test:8188/models/loras").mock(
            return_value=httpx.Response(200, json=["detail.safetensors"])
        )
        warnings = await checker.check_models(workflow, client)
        assert warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_model_checker.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement ModelChecker**

Create `src/comfyui_mcp/security/model_checker.py`:

```python
"""Proactive model availability checker for workflow submission."""

from __future__ import annotations

from typing import Any

import httpx

from comfyui_mcp.client import ComfyUIClient

# Maps node class_type -> (input field name, model folder)
_MODEL_LOADER_FIELDS: dict[str, tuple[str, str]] = {
    "CheckpointLoaderSimple": ("ckpt_name", "checkpoints"),
    "CheckpointLoader": ("ckpt_name", "checkpoints"),
    "unCLIPCheckpointLoader": ("ckpt_name", "checkpoints"),
    "LoraLoader": ("lora_name", "loras"),
    "LoraLoaderModelOnly": ("lora_name", "loras"),
    "VAELoader": ("vae_name", "vae"),
    "ControlNetLoader": ("control_net_name", "controlnet"),
    "UpscaleModelLoader": ("model_name", "upscale_models"),
    "CLIPLoader": ("clip_name", "clip"),
    "CLIPVisionLoader": ("clip_name", "clip_vision"),
    "StyleModelLoader": ("style_model_name", "style_models"),
    "GLIGENLoader": ("gligen_name", "gligen"),
    "DiffusersLoader": ("model_path", "diffusers"),
    "UNETLoader": ("unet_name", "diffusion_models"),
    "DualCLIPLoader": ("clip_name1", "clip"),
    "TripleCLIPLoader": ("clip_name1", "clip"),
    "PhotoMakerLoader": ("photomaker_model_name", "photomaker"),
    "IPAdapterModelLoader": ("ipadapter_file", "ipadapter"),
}


class ModelChecker:
    """Checks workflow loader nodes against installed models."""

    async def check_models(
        self, workflow: dict[str, Any], client: ComfyUIClient
    ) -> list[str]:
        """Check all model loader nodes in a workflow for missing models.

        Returns a list of warning strings for any missing models.
        Silently returns empty list on API errors (best-effort check).
        """
        # Collect (model_name, folder) pairs to check
        to_check: list[tuple[str, str]] = []

        for node_data in workflow.values():
            if not isinstance(node_data, dict):
                continue
            class_type = node_data.get("class_type", "")
            if class_type not in _MODEL_LOADER_FIELDS:
                continue

            field_name, folder = _MODEL_LOADER_FIELDS[class_type]
            inputs = node_data.get("inputs", {})
            model_name = inputs.get(field_name)

            # Skip node references (lists like ["4", 0]) and non-string values
            if not isinstance(model_name, str) or not model_name:
                continue

            to_check.append((model_name, folder))

        if not to_check:
            return []

        # Fetch installed models per folder (cached per call)
        folder_models: dict[str, set[str]] = {}
        warnings: list[str] = []

        for model_name, folder in to_check:
            if folder not in folder_models:
                try:
                    models = await client.get_models(folder)
                    folder_models[folder] = set(models)
                except (httpx.HTTPError, OSError):
                    # API error — skip this folder check
                    folder_models[folder] = set()
                    continue

            if model_name not in folder_models[folder]:
                warnings.append(
                    f"Missing model: '{model_name}' not found in {folder}. "
                    f"Use search_models to find and download_model to install it."
                )

        return warnings

    # NOTE: The spec mentions fuzzy matching for nodes with fields ending in `_name`.
    # This is deferred to a follow-up — the static _MODEL_LOADER_FIELDS mapping
    # covers all standard ComfyUI loaders. Fuzzy matching risks false positives
    # (e.g. "sampler_name" is not a model reference) and needs a curated exclusion
    # list. See spec section "Plus fuzzy matching" for requirements.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_model_checker.py -v`
Expected: PASS

- [ ] **Step 5: Run lint and type check**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/security/model_checker.py tests/test_model_checker.py
git commit -m "feat(security): add proactive model availability checker"
```

---

### Task 9: Integrate model checker into generation tools

**Files:**
- Modify: `src/comfyui_mcp/tools/generation.py:145-154` (register_generation_tools signature)
- Modify: `src/comfyui_mcp/server.py` (pass model_checker to generation tools)
- Test: `tests/test_tools_generation.py` (add model check tests)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tools_generation.py` (or create test class):

```python
# Add to tests/test_tools_generation.py

class TestModelCheckIntegration:
    @respx.mock
    async def test_run_workflow_warns_missing_model(self, components):
        """run_workflow should include missing model warnings."""
        # Mock the models endpoint to return empty list
        respx.get("http://test:8188/models/checkpoints").mock(
            return_value=httpx.Response(200, json=["other_model.safetensors"])
        )
        # Mock prompt submission
        respx.post("http://test:8188/prompt").mock(
            return_value=httpx.Response(200, json={"prompt_id": "abc-123"})
        )

        workflow = json.dumps({
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "missing_model.safetensors"},
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {"model": ["4", 0]},
            },
        })
        result = await components["tools"]["run_workflow"](workflow=workflow)
        assert "Missing model" in result
        assert "missing_model.safetensors" in result
        assert "search_models" in result
```

Note: The exact fixture setup depends on the existing test structure in `test_tools_generation.py`. The test must create a `ModelChecker` and pass it to `register_generation_tools`. Read the existing test file first to match the pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools_generation.py::TestModelCheckIntegration -v`
Expected: FAIL — `register_generation_tools` doesn't accept `model_checker` yet

- [ ] **Step 3: Integrate model checker**

Modify `src/comfyui_mcp/tools/generation.py`:

Add import:
```python
from comfyui_mcp.security.model_checker import ModelChecker
```

Update `register_generation_tools` signature to accept optional `model_checker`:
```python
def register_generation_tools(
    mcp: FastMCP,
    client: ComfyUIClient,
    audit: AuditLogger,
    limiter: RateLimiter,
    inspector: WorkflowInspector,
    *,
    read_limiter: RateLimiter | None = None,
    progress: WebSocketProgress | None = None,
    model_checker: ModelChecker | None = None,
) -> dict[str, Any]:
```

In `run_workflow`, after the `inspector.inspect()` call and **before** the audit log for "inspected", add:
```python
        # Proactive model availability check
        if model_checker is not None:
            model_warnings = await model_checker.check_models(wf, client)
            if model_warnings:
                inspection.warnings.extend(model_warnings)
                # In enforce mode, block submission for missing models
                if inspector._mode == "enforce":
                    raise WorkflowBlockedError(
                        f"Workflow blocked — missing models: {model_warnings}"
                    )
```

Then the existing `audit.log(... action="inspected", warnings=inspection.warnings ...)` call
will include both security warnings AND missing-model warnings in the audit trail.

In `generate_image`, after the `inspector.inspect()` call and **before** the audit log, add the same check:
```python
        # Proactive model availability check
        if model_checker is not None:
            model_warnings = await model_checker.check_models(wf, client)
            if model_warnings:
                inspection.warnings.extend(model_warnings)
                if inspector._mode == "enforce":
                    raise WorkflowBlockedError(
                        f"Workflow blocked — missing models: {model_warnings}"
                    )
```

Note: Accessing `inspector._mode` is a private attribute. To avoid this, add a `@property`
to `WorkflowInspector`:
```python
    @property
    def mode(self) -> str:
        return self._mode
```

Then use `inspector.mode` instead of `inspector._mode` in the checks above.

The server.py wiring for ModelChecker is already handled in Task 7 (created in `_build_server`,
passed through `_register_all_tools` to `register_generation_tools`).

Update the `register_generation_tools` call in `_register_all_tools` (already done in Task 7):
```python
    register_generation_tools(
        server,
        client,
        audit,
        rate_limiters["generation"],
        inspector,
        read_limiter=rate_limiters["read"],
        progress=progress,
        model_checker=model_checker,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tools_generation.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite, lint, and type check**

Run: `uv run pytest -v && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run mypy src/comfyui_mcp/`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/comfyui_mcp/tools/generation.py src/comfyui_mcp/server.py tests/test_tools_generation.py
git commit -m "feat(generation): integrate proactive model availability check"
```

---

### Task 10: Update README tools table

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add new tools to README tools table**

Add the following rows to the tools table in `README.md`:

| Tool | Description |
|------|-------------|
| `search_models` | Search HuggingFace or CivitAI for models |
| `download_model` | Download a model via ComfyUI-Model-Manager |
| `get_download_tasks` | Check status of active model downloads |
| `cancel_download` | Cancel a model download task |

Also add a note about the ComfyUI-Model-Manager dependency requirement.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add model search/download tools to README"
```
