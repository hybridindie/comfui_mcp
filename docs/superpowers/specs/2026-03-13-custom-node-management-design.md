# Custom Node Management with Security Auditing

**Issue:** #15
**Date:** 2026-03-13
**Status:** Approved

## Goal

Add tools to search, install, update, and uninstall ComfyUI custom nodes via ComfyUI Manager, with automatic security auditing of newly installed nodes after restart. Registry-only installs (no arbitrary git URLs).

## Background

ComfyUI Manager (`Comfy-Org/ComfyUI-Manager`) provides a queue-based API for custom node lifecycle management. Operations are queued, then processed by a worker thread. Node installations require a ComfyUI restart to take effect.

The MCP server already has `NodeAuditor` infrastructure that scans installed nodes for dangerous patterns (exec, eval, subprocess, etc.) via the `audit_dangerous_nodes` tool. This design extends that by automatically auditing after node installation when a restart is performed.

### ComfyUI Manager API (relevant endpoints)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/manager/version` | Check Manager availability |
| GET | `/customnode/getlist?mode=remote` | Search/list registry nodes |
| GET | `/customnode/installed` | List installed node packs |
| POST | `/manager/queue/install` | Queue node installation |
| POST | `/manager/queue/uninstall` | Queue node removal |
| POST | `/manager/queue/update` | Queue node update |
| GET | `/manager/queue/start` | Start processing queued tasks |
| GET | `/manager/queue/status` | Poll queue progress |
| GET | `/manager/reboot` | Restart ComfyUI |

Queue endpoints accept JSON with `id` and `version` fields. The `ui_id` field is used for Manager UI progress tracking and can be omitted by API callers — it is optional. The queue is processed sequentially by a worker thread started via `/manager/queue/start`.

**Note on `/manager/reboot`:** This endpoint uses GET (unusual for a destructive action) — this is upstream ComfyUI Manager behavior. We permit this endpoint because it is only called when the user explicitly passes `restart=True` and the job queue is verified empty. It is not added to the blocked endpoints list in CLAUDE.md because it requires user opt-in and has the queue safety gate.

## Architecture

### New file: `src/comfyui_mcp/node_manager.py`

`ComfyUIManagerDetector` — lazy-probe singleton following the `ModelManagerDetector` pattern in `model_manager.py`.

- Probes `GET /manager/version` on first use
- Caches availability flag and version string behind `asyncio.Lock`
- `is_available() -> bool` — probe once, cache result
- `require_available()` — raise `ComfyUIManagerUnavailableError` if not installed
- Error message tells the user how to install ComfyUI Manager

### New client methods: `src/comfyui_mcp/client.py`

Eight new methods on `ComfyUIClient`:

```
get_manager_version() -> str
    GET /manager/version
    Returns version string. Used by detector probe.

get_custom_node_list(mode: str = "remote") -> dict
    GET /customnode/getlist?mode={mode}
    Returns {"channel": str, "node_packs": dict}.

queue_custom_node_install(node_id: str, version: str = "") -> None
    POST /manager/queue/install
    Body: {"id": node_id, "version": version}

queue_custom_node_uninstall(node_id: str, version: str = "") -> None
    POST /manager/queue/uninstall
    Body: {"id": node_id, "version": version}

queue_custom_node_update(node_id: str, version: str = "") -> None
    POST /manager/queue/update
    Body: {"id": node_id, "version": version}

start_custom_node_queue() -> None
    GET /manager/queue/start

get_custom_node_queue_status() -> dict
    GET /manager/queue/status
    Returns {"total_count", "done_count", "in_progress_count", "is_processing"}.

reboot_comfyui() -> None
    GET /manager/reboot
```

All methods use `self._request()` for retry logic. Queue body payloads send `node_id` in JSON (not interpolated into URLs). The `mode` parameter on `get_custom_node_list` is validated via `_validate_path_segment()` since it is interpolated into query strings.

Note: `get_installed_custom_nodes()` is deliberately omitted — the remote node list from `get_custom_node_list()` already includes install status per node. Adding it would violate CLAUDE.md rule 8 (no dead code) since no tool needs it. Can be added later if a `list_installed_nodes` tool is needed.

### New tool file: `src/comfyui_mcp/tools/nodes.py`

`register_node_tools(mcp, client, audit, wf_limiter, read_limiter, node_manager, node_auditor)` returns a `dict[str, Any]` of 5 tool functions. Two rate limiters: `wf_limiter` for mutations (install/uninstall/update), `read_limiter` for queries (search/status).

#### `search_custom_nodes(query: str) -> str`

Search the ComfyUI Manager registry for custom nodes.

1. `read_limiter.check("search_custom_nodes")`
2. `node_manager.require_available()`
3. `audit.async_log(tool="search_custom_nodes", action="searching", extra={"query": query})`
4. Call `client.get_custom_node_list(mode="remote")`
5. Filter `node_packs` by query (case-insensitive match against name, description, author)
6. Return formatted results: name, description, author, install status, ID (for use with install)
7. Cap results at 10 to avoid overwhelming context (consistent with `search_models`)

#### `install_custom_node(id: str, version: str = "", restart: bool = False) -> str`

Install a custom node pack from the registry.

1. `wf_limiter.check("install_custom_node")`
2. `node_manager.require_available()`
3. Validate `id`: non-empty, no control characters, max 200 chars
4. `audit.async_log(tool="install_custom_node", action="installing", extra={"id": id, "version": version})`
5. Call `client.queue_custom_node_install(id, version)`
6. Call `client.start_custom_node_queue()`
7. Poll `client.get_custom_node_queue_status()` every 2s until `is_processing` is False (timeout: 300s)
8. If `restart=True`:
   a. Check `client.get_queue()` for running/pending jobs
   b. If jobs active: return install success + "Restart deferred — N jobs in queue. Restart manually, then run `audit_dangerous_nodes`."
   c. If queue empty: call `client.reboot_comfyui()`
   d. Poll ComfyUI availability (retry `client.get_queue()` every 3s with timeout 60s)
   e. Wait 5s after first successful response for node loading to complete
   f. Fetch `client.get_object_info()`, run `node_auditor.audit_all_nodes()`, include findings in response
9. If `restart=False`: return install success + "Restart required for nodes to become active."
10. `audit.async_log(tool="install_custom_node", action="completed", extra={...})`

The queue→start→poll→restart+audit flow is shared with `update_custom_node`. Extract as `_execute_node_operation(client, action_fn, restart, node_auditor)` helper to avoid duplication (similar to `_submit_workflow()` in generation tools).

#### `uninstall_custom_node(id: str, restart: bool = False) -> str`

Uninstall a custom node pack.

Same pattern as install: queue → start → poll → optional restart. No post-restart audit needed (nodes are being removed).

#### `update_custom_node(id: str, restart: bool = False) -> str`

Update a custom node pack.

Same pattern as install: queue → start → poll → optional restart. Post-restart audit included (updated code could introduce new patterns).

#### `get_custom_node_status() -> str`

Check the custom node operation queue.

1. `read_limiter.check("get_custom_node_status")`
2. `node_manager.require_available()`
3. `audit.async_log(tool="get_custom_node_status", action="checking")`
4. Call `client.get_custom_node_queue_status()`
5. Return formatted status: total tasks, completed, in progress, whether processing

### Wiring: `src/comfyui_mcp/server.py`

In `_build_server()`:
1. Create `ComfyUIManagerDetector(client)` — lazy, no startup cost
2. Create `NodeAuditor()` (already exists for discovery tools)
3. Call `register_node_tools(mcp, client, audit, wf_limiter, read_limiter, node_manager, node_auditor)` — pass both rate limiters; reuse the existing `NodeAuditor` instance shared with `register_discovery_tools()`
4. Add `node_manager` and `node_auditor` parameters to `_register_all_tools()` signature
4. Merge returned dict into tool registry

### Rate limiting

Use the `workflow` rate limiter (10/min default) for install, uninstall, update — these are heavy operations. Use `read_only` limiter (60/min) for search and status.

### Security controls

| Control | How applied |
|---------|-------------|
| Rate limiting | `workflow` limiter for mutations, `read_only` for queries |
| Audit logging | Every tool call logged with structured data |
| Manager availability | Lazy probe, helpful error if missing |
| Registry-only | No arbitrary git URL installs — only registry IDs |
| Post-install audit | Automatic `NodeAuditor` scan after restart |
| Restart safety | Queue checked before reboot — deferred if jobs running |
| Input validation | Node IDs validated (non-empty, no control chars, max 200 chars) and sent in JSON body (not URL paths) |

### Error handling

- ComfyUI Manager not installed → `ComfyUIManagerUnavailableError` with install instructions
- Queue poll timeout (default 300s) → return partial result: "Operation queued but not yet complete. Use `get_custom_node_status` to check progress."
- Restart poll timeout (60s) → return "ComfyUI restarting — not yet reachable. Check back shortly."
- Node ID not found in registry → ComfyUI Manager returns 404; surface as "Node pack '{id}' not found in registry. Use `search_custom_nodes` to find available packs."
- `version` parameter: empty string (default) installs the latest version. Non-empty values are passed to ComfyUI Manager as-is (it handles version resolution internally). Document this in tool docstrings.

## Testing

### Unit tests: `tests/test_node_manager.py`

- `ComfyUIManagerDetector`: probe success, probe failure (not installed), probe caches result, concurrent probe uses lock
- `ComfyUIManagerUnavailableError`: message includes install instructions

### Unit tests: `tests/test_tools_nodes.py`

- `search_custom_nodes`: returns filtered results, empty query returns all, handles no results
- `install_custom_node`: queues + starts + polls, restart=False returns restart message, restart=True with empty queue reboots and audits, restart=True with busy queue defers
- `uninstall_custom_node`: queues + starts + polls, restart logic
- `update_custom_node`: queues + starts + polls, restart + audit logic
- `get_custom_node_status`: returns formatted queue status
- All tools: rate limiter called, audit logged, manager unavailable raises error

### Client tests: `tests/test_client.py`

- New methods: `get_manager_version`, `get_custom_node_list`, `queue_custom_node_install`, `queue_custom_node_uninstall`, `queue_custom_node_update`, `start_custom_node_queue`, `get_custom_node_queue_status`, `reboot_comfyui`
- All with `@respx.mock`

## File map

| File | Action | Purpose |
|------|--------|---------|
| `src/comfyui_mcp/node_manager.py` | Create | ComfyUIManagerDetector (lazy probe) |
| `src/comfyui_mcp/client.py` | Modify | Add 7 new client methods |
| `src/comfyui_mcp/tools/nodes.py` | Create | 5 new tools |
| `src/comfyui_mcp/server.py` | Modify | Wire node_manager + register_node_tools |
| `tests/test_node_manager.py` | Create | Detector tests |
| `tests/test_tools_nodes.py` | Create | Tool tests |
| `tests/test_client.py` | Modify | Client method tests |
| `README.md` | Modify | Add tools to table, document feature |

## Out of scope

- Arbitrary git URL installs (security risk, can be added later)
- `pip` package installs via `/customnode/install/pip` (too dangerous)
- ComfyUI version management (separate concern)
- Snapshot management (separate concern)
- Enable/disable nodes (low priority, can be added later)
