# Model Search & Download — Design Spec

## Summary

Add tools to search HuggingFace/CivitAI for models and download them via ComfyUI-Model-Manager, with proactive missing-model detection during workflow submission.

## Motivation

Model download is the biggest workflow friction point. An LLM can recommend a model but can't help install it. This feature closes that gap by leveraging ComfyUI-Model-Manager's existing download infrastructure.

## Architecture

The MCP server acts as a thin orchestration layer:

- **Search**: MCP server calls HuggingFace/CivitAI REST APIs directly via `httpx`
- **Download**: MCP server forwards to Model Manager's API (`POST /model-manager/model`)
- **Progress/Cancel**: MCP server proxies Model Manager's task endpoints
- **Proactive check**: Before workflow submission, cross-references loader nodes against installed models

No new dependencies. No filesystem access. Model Manager handles streaming, resumable downloads, and disk writes.

## Dependency: ComfyUI-Model-Manager

- Repository: https://github.com/hayden-fr/ComfyUI-Model-Manager
- Well maintained: 184 stars, 15 contributors, 493 commits, 36 releases
- Exposes REST API on ComfyUI's server:
  - `POST /model-manager/model` — create download task
  - `GET /model-manager/download/task` — list tasks with progress
  - `DELETE /model-manager/download/{task_id}` — cancel
  - `GET /model-manager/models` — list folders
  - `GET /model-manager/models/{folder}` — list models in folder
- No domain restrictions on downloads — our MCP server provides the security boundary

Note: Model Manager also exposes `PUT /model-manager/download/{task_id}` for pause/resume. We do not wrap this endpoint — users can pause/resume via Model Manager's UI directly. If demand arises, a `pause_download` tool can be added later.

## Detection

Detection uses **lazy initialization** to avoid changing `_build_server()`'s synchronous signature (per CLAUDE.md rule 10). A `ModelManagerDetector` helper is created at startup with the client reference. On the first invocation of any model tool, it runs the async probe and caches the result. Subsequent calls use the cached value.

1. On first model tool call, probe `GET /model-manager/models` on the ComfyUI server
2. If 200: cache available folders, allow tool execution
3. If error: raise with message "ComfyUI-Model-Manager not detected. Install: https://github.com/hayden-fr/ComfyUI-Model-Manager"
4. All four tools are registered at startup but gated behind the detector — if Model Manager is absent, they return a clear error on first use

The canonical folder list comes from **Model Manager's `GET /model-manager/models`**, not ComfyUI's native `GET /models`. This is the authoritative source for what folders Model Manager can download into. If the probe fails, no model tools function.

## Tools

All tools follow CLAUDE.md rules: rate limiting, audit logging (start + end actions with structured data), path sanitization.

### `search_models(query, source, model_type, limit)`

- `source`: "civitai" (default) or "huggingface"
- Calls CivitAI `GET https://civitai.com/api/v1/models` or HuggingFace `GET https://huggingface.co/api/models`
- For HuggingFace, fetches model detail to get file list and sizes
- Returns: name, URL, size, download count, type
- Rate limited: `read` (60/min)
- Audit logged: query, source, result count
- Passes configured API keys as auth headers

### `download_model(url, folder, filename)`

- Validates URL hostname against `allowed_download_domains`
- Validates URL path matches known direct-download patterns (see Security section)
- Validates folder via `PathSanitizer.validate_path_segment()` first, then checks against Model Manager's cached folder list (fail closed — reject if folder not in list)
- Validates filename through `PathSanitizer.validate_filename()`
- Validates file extension against `allowed_model_extensions`
- Calls `POST /model-manager/model` on ComfyUI
- Returns: task ID and status
- Rate limited: `file` (30/min)
- Audit logged: url, folder, filename, task_id

### `get_download_tasks()`

- Proxies `GET /model-manager/download/task`
- Returns: list of tasks with downloadedSize, totalSize, bps, status
- Rate limited: `read` (60/min)
- Audit logged: task count returned

### `cancel_download(task_id)`

- Calls `DELETE /model-manager/download/{task_id}`
- Rate limited: `file` (30/min)
- Audit logged: task_id

## Proactive Model Check

Added to the workflow submission flow in `generation.py`, after `inspector.inspect()`:

1. Extract model references from loader nodes using a node-to-folder mapping
2. For each referenced model, check against installed models via `client.get_models(folder)`
3. If missing, add warnings: "Missing model: 'x.safetensors' in checkpoints. Use search_models to find and download_model to install it."
4. Audit mode: warn but submit. Enforce mode: block submission.

### Node-to-folder mapping

Static mapping for known loaders:

| Node class_type | Field | Folder |
|---|---|---|
| CheckpointLoaderSimple | ckpt_name | checkpoints |
| LoraLoader | lora_name | loras |
| VAELoader | vae_name | vae |
| ControlNetLoader | control_net_name | controlnet |
| UpscaleModelLoader | model_name | upscale_models |
| CLIPLoader | clip_name | clip |
| CLIPVisionLoader | clip_name | clip_vision |
| StyleModelLoader | style_model_name | style_models |
| GLIGENLoader | gligen_name | gligen |
| unCLIPCheckpointLoader | ckpt_name | checkpoints |
| DiffusersLoader | model_path | diffusers |

Plus fuzzy matching: nodes with fields ending in `_name` whose values don't match any installed model across known folders get flagged.

Available folders fetched from Model Manager's `GET /model-manager/models` (canonical source, same as detection). Falls back to ComfyUI's `GET /models` if Model Manager is unavailable (proactive check still works without Model Manager — it just can't suggest downloading).

## Configuration

### New: `ModelSearchSettings`

```yaml
model_search:
  huggingface_token: ""       # Optional, for gated models
  civitai_api_key: ""         # Optional, for some CivitAI queries
  max_search_results: 10      # Cap results returned
```

Env overrides: `COMFYUI_HUGGINGFACE_TOKEN`, `COMFYUI_CIVITAI_API_KEY`, `COMFYUI_MAX_SEARCH_RESULTS`

### Extended: `SecuritySettings`

```yaml
security:
  allowed_download_domains:
    - huggingface.co
    - civitai.com
  allowed_model_extensions:
    - .safetensors
    - .ckpt
    - .pt
    - .pth
    - .bin
```

Env override: `COMFYUI_ALLOWED_DOWNLOAD_DOMAINS` (comma-separated)

API keys are sensitive fields — auto-redacted by audit logger.

## Security

- **Domain allowlist** enforced by MCP server before forwarding to Model Manager (which has no domain restrictions). Configurable to support private model registries.
- **URL path validation** — beyond domain checking, URLs are validated against known direct-download patterns (`https://huggingface.co/*/resolve/*` for HuggingFace, `https://civitai.com/api/download/*` for CivitAI). This mitigates open-redirect risk: even if an allowlisted domain redirects, our initial URL must match the expected download path pattern. Note: Model Manager follows redirects server-side, so this is defense-in-depth, not a complete guarantee. This limitation is accepted — the primary threat model is preventing the LLM from being tricked into downloading from arbitrary domains.
- **Extension allowlist** validated before download
- **Path sanitization** on folder and filename via PathSanitizer. Folder validation order: `validate_path_segment()` first (safety), then Model Manager folder allowlist (business logic). If Model Manager's folder list is unavailable, fail closed (reject).
- **Rate limiting** per tool (read or file category)
- **Audit logging** on every tool invocation with start/end actions and structured extra data
- **No filesystem access** — Model Manager handles all disk writes
- **No new attack surface** — external API calls are read-only GETs to allowlisted domains

## File Changes

### New files
- `src/comfyui_mcp/tools/models.py` — four tools via `register_model_tools()`
- `tests/test_tools_models.py` — tool tests
- `tests/test_model_check.py` — proactive model check tests

### Modified files
- `src/comfyui_mcp/config.py` — `ModelSearchSettings`, extended `SecuritySettings`, env overrides
- `src/comfyui_mcp/client.py` — Model Manager client methods
- `src/comfyui_mcp/server.py` — lazy detector creation, tool registration, folder caching
- `src/comfyui_mcp/security/inspector.py` — `check_models()` method
- `src/comfyui_mcp/tools/generation.py` — call `check_models()` after `inspect()`

### No new dependencies
