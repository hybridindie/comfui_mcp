# WebSocket Progress Tracking — Design Spec

## Overview

Add real-time progress tracking for workflow execution via ComfyUI's WebSocket API. Introduces a `wait` parameter on `run_workflow` and `generate_image` for blocking execution with structured results, and a `get_progress` tool for polling with richer data than `get_job`. Addresses issue #3.

## Approach

On-demand WebSocket connections with HTTP fallback. No persistent connection — WebSocket connects only when needed (`wait=true`) and disconnects on completion. `get_progress` falls back to HTTP (`/queue`, `/history`) when no WebSocket is active.

## Tool Changes

### `run_workflow(workflow_json, wait=False)` — modified

New optional `wait` parameter (bool, default `False`).

When `wait=true`:
- Submits workflow via HTTP (`post_prompt`)
- Opens WebSocket to `/ws?clientId={uuid}`
- Listens for progress/executing/executed events until completion or error
- Returns structured result:
  - `prompt_id`: string
  - `status`: `"completed"` | `"error"` | `"timeout"`
  - `elapsed_seconds`: float
  - `outputs`: list of `{node_id, filename, subfolder}`
  - `warnings`: list of strings
- Timeout: uses existing `timeout_read` setting (300s default). Returns `status: "timeout"` if exceeded.
- On WebSocket failure: falls back to HTTP polling of `/history/{prompt_id}`

When `wait=false` (default): current behavior unchanged — returns `prompt_id` string.

### `generate_image(..., wait=False)` — modified

Same `wait` parameter (bool), same blocking/result behavior as `run_workflow`.

### `get_progress(prompt_id)` — new tool

Registered in `tools/jobs.py`. Returns unified progress structure:

- `prompt_id`: string
- `status`: `"queued"` | `"running"` | `"completed"` | `"error"` | `"unknown"`
- `queue_position`: int (when queued)
- `current_node`: string — class_type of executing node (when running, WebSocket only)
- `step`: int — current sampling step (when running, WebSocket only)
- `total_steps`: int (when running, WebSocket only)
- `elapsed_seconds`: float (when running or completed)
- `outputs`: list of `{node_id, filename, subfolder}` (when completed)

If no active WebSocket, `step`/`total_steps`/`current_node` are omitted. Remaining fields come from HTTP (`/queue` for position, `/history/{prompt_id}` for completion/outputs).

Rate limited under `read` category. Audit logged.

## Module Structure

### New module: `src/comfyui_mcp/progress.py`

Contains:
- `ProgressState` — dataclass for the unified progress structure
- `WebSocketProgress` — manages on-demand WebSocket connections, event parsing, HTTP fallback

`WebSocketProgress` responsibilities:
- `wait_for_completion(prompt_id)` — connect WebSocket, listen for events until done, return final state. Falls back to HTTP polling on WebSocket failure.
- `get_state(prompt_id)` — return current `ProgressState` via HTTP (`/queue` + `/history`). Step/node fields omitted (HTTP-only).
- Internal `client_id` generated as UUID per instance
- Constructor takes `client: ComfyUIClient`, `timeout: float` (from settings `timeout_read`), and `tls_verify: bool` (matches client TLS settings)

Depends on: `websockets` library, `comfyui_mcp.client.ComfyUIClient` (for HTTP fallback and base URL).
Does not import from `tools/`.

### URL scheme translation

`WebSocketProgress` derives the WebSocket URL from `client.base_url` by replacing `http://` → `ws://` and `https://` → `wss://`, then appending `/ws?clientId={uuid}`. This is done internally — no new config fields needed.

### Why separate from `client.py`

HTTP client is request/response. WebSocket is connect/listen/disconnect — different lifecycle. Keeping them separate maintains clarity in both.

### Wiring in `server.py`

```python
progress = WebSocketProgress(client, timeout=settings.comfyui.timeout_read)
register_generation_tools(
    server, client, audit, rate_limiters["generation"], inspector,
    read_limiter=rate_limiters["read"], progress=progress,
)
register_job_tools(server, client, audit, rate_limiters["workflow"], progress=progress)
```

Note: `register_job_tools` keeps its existing `rate_limiters["workflow"]` limiter for mutation tools (`cancel_job`, `interrupt`, `clear_queue`). The new `get_progress` tool uses a separate `rate_limiters["read"]` limiter passed via the `progress` object or as an additional parameter.

## New dependency

`websockets>=15.0` — async WebSocket client. Lightweight, no transitive dependencies.

## ComfyUI WebSocket Protocol

ComfyUI's `/ws?clientId={id}` pushes JSON messages:

- `{type: "progress", data: {value: 5, max: 20}}` — sampling step progress
- `{type: "executing", data: {node: "3"}}` — which node is running (null node = done)
- `{type: "executed", data: {node: "7", output: {images: [...]}}}` — node output
- `{type: "execution_error", data: {...}}` — execution failure

## Security Compliance

- `get_progress` calls `limiter.check()` and `audit.log()`
- `client_id` is UUID, generated internally — never user-supplied
- WebSocket connects to same `comfyui.url` (scheme translated `http`→`ws`, `https`→`wss`) — no new endpoints exposed
- `wait=true` path still runs `inspector.inspect()` before submission (existing behavior)
- No blocked endpoints added

## Testing

Test files: `tests/test_progress.py`, updates to `tests/test_tools_generation.py` and `tests/test_tools_jobs.py`.

- **WebSocket lifecycle:** Mock WebSocket with async context manager fake. Test connect → receive events → state updates → disconnect.
- **`wait=true` flow:** Mocked WebSocket + mocked HTTP submission. Verify structured result.
- **Timeout:** Verify `status: "timeout"` when `timeout_read` exceeded.
- **`get_progress` HTTP fallback:** Use `respx` mocks for `/queue` and `/history`. Verify unified structure without WebSocket fields.
- **WebSocket failure graceful degradation:** Connection refused → falls back to HTTP polling, no crash.
- **Backward compatibility:** `wait=false` (default) returns same format as before.

Tests should use `respx` mocks for HTTP and a simple async fake for WebSocket. No real connections.
