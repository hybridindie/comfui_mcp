# CLAUDE.md — ComfyUI MCP Server

## Project Overview

A secure MCP (Model Context Protocol) server for ComfyUI. Enables AI assistants like Claude to generate images, run workflows, and manage jobs through ComfyUI with built-in security controls:
- Workflow Inspector (detects dangerous nodes like `eval`, `exec`)
- Path Sanitizer (blocks path traversal attacks)
- Rate Limiter (token-bucket per tool category)
- Audit Logger (structured JSON logging)
- Selective API surface (blocks dangerous endpoints)

## Tech Stack

- **Python**: 3.12
- **Package Manager**: uv
- **MCP SDK**: mcp[cli] (FastMCP)
- **HTTP Client**: httpx (async)
- **Validation**: pydantic
- **Config**: pyyaml

## Project Structure

```
src/comfyui_mcp/
├── server.py              # MCP server entry, wires all components
├── config.py              # Pydantic settings, YAML loading, env overrides
├── client.py              # Async HTTP client for ComfyUI API
├── audit.py               # Structured JSON audit logger
├── model_manager.py       # Lazy Model Manager detection and folder caching
├── progress.py            # WebSocket progress tracking with HTTP polling fallback
├── security/
│   ├── inspector.py       # Workflow node inspection (audit/enforce)
│   ├── node_auditor.py    # Scans installed nodes for dangerous patterns
│   ├── sanitizer.py       # File path validation
│   ├── rate_limit.py      # Token-bucket rate limiter
│   ├── download_validator.py  # URL domain/path and extension validation
│   └── model_checker.py   # Proactive model availability checking
├── workflow/
│   ├── templates.py       # Built-in workflow templates (txt2img, img2img, etc.)
│   ├── operations.py      # Workflow graph operations (add/remove nodes, connect)
│   └── validation.py      # Workflow analysis and validation
└── tools/
    ├── generation.py      # generate_image, run_workflow, summarize_workflow
    ├── workflow.py        # create_workflow, modify_workflow, validate_workflow
    ├── jobs.py            # get_queue, get_job, cancel_job, interrupt, get_progress
    ├── discovery.py       # list_models, list_nodes, audit_dangerous_nodes, etc.
    ├── history.py         # get_history
    ├── files.py           # upload_image, get_image, list_outputs, upload_mask
    └── models.py          # search_models, download_model, get_download_tasks, cancel_download

scripts/
└── smoke_test.py          # Operator smoke-test against a live ComfyUI instance

tests/                     # pytest with asyncio_mode = auto
pyproject.toml            # Project config (hatchling build)
```

## Development Commands

```bash
uv sync                    # Install dependencies
uv run pytest -v           # Run tests
uv run pytest --cov=src/comfyui_mcp --cov-report=term-missing  # Coverage
uv run ruff check src/ tests/         # Lint
uv run ruff format src/ tests/        # Format (in-place)
uv run ruff format --check src/ tests/  # Format check (CI)
uv run mypy src/comfyui_mcp/          # Type check
uv run pre-commit run --all-files     # Run all pre-commit hooks

# Smoke-test against a live ComfyUI instance
uv run python scripts/smoke_test.py                          # Full (connectivity + folders + download)
uv run python scripts/smoke_test.py --no-download            # Connectivity + folder listing only
uv run python scripts/smoke_test.py --url http://host:8188   # Target a specific server
```

## Rules

### Security rules

These are non-negotiable. This is a security-focused project.

1. **Never expose blocked ComfyUI endpoints.** The following are deliberately excluded: `/userdata`, `/free`, `/users`, `/history` POST (delete). They must never be added to `client.py`. Before adding any new client method, verify the endpoint is not on this list.
    `/system_stats` is a special case: it **may** be called internally by `get_system_stats()` in `client.py`, but **only** to serve the `get_system_info` tool, which applies a strict output whitelist (GPU VRAM, queue counts, ComfyUI version only). No raw `/system_stats` response is ever returned to any caller. Do not add any other callers of `get_system_stats()`.
2. **All file-handling tools must use PathSanitizer.** Every tool that accepts a filename or subfolder parameter must call `sanitizer.validate_filename()` and/or `sanitizer.validate_subfolder()` before passing values to the client. No exceptions.
3. **All tools must go through the rate limiter.** Every tool function must call `limiter.check("tool_name")` before doing any work.
4. **All tools must audit log.** Every tool function must call `audit.log(tool="...", action="...")` with structured data. Sensitive fields are auto-redacted but never log raw user secrets intentionally.
5. **Workflow execution must go through the inspector.** Any tool that submits a workflow via `client.post_prompt()` must first call `inspector.inspect()` and include warnings in the response.
6. **No new dependencies without a real import.** Every dependency in `pyproject.toml` must be imported somewhere in `src/`. Do not add speculative or "might need later" dependencies.

### Lint and format rules

17. **All code must pass `ruff check` and `ruff format --check`.** Run `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` before committing. Ruff auto-fix (`--fix`) is safe to use.
18. **All source code must pass `mypy`.** Run `uv run mypy src/comfyui_mcp/` before committing. Add type annotations to new code. Use `# type: ignore[code]` only when the type stub is wrong, and always include the specific error code.
19. **Pre-commit hooks must pass.** Run `uv run pre-commit run --all-files` to verify. Hooks are installed via `uv run pre-commit install`.

### Code rules

7. **No duplicate tools.** Each tool must have a unique purpose. Before adding a new tool, check if an existing tool already covers the same ComfyUI endpoint. Two tools calling the same client method is a bug.
8. **No dead code.** No placeholder methods, no unused config fields, no unreachable branches. If a field or method isn't used, don't add it. If it stops being used, remove it.
9. **All imports at the top of the file.** No deferred imports inside function bodies unless the dependency is optional and heavy. stdlib modules are never deferred.
10. **`_build_server()` returns `tuple[FastMCP, Settings]`.** The module-level `mcp` and `_settings` are built once. `main()` reuses `_settings` — never call `load_settings()` a second time.
11. **Tool registration functions return `dict[str, Any]`.** Every `register_*_tools()` must return a dict mapping tool names to their callable functions. This is how tests invoke tools directly.

### Test rules

12. **Tests must call actual tool functions.** Test tools by calling the functions returned from `register_*_tools()`, or by using the tool registration dict. Never access `_tool_manager` or other private SDK attributes.
13. **Tests must test this project, not libraries.** Don't test that pydantic validates types, that respx mocks work, or that FastMCP registers tools. Test that *our* code does the right thing: security checks block bad input, audit logs are written, correct API calls are made.
14. **No `@pytest.mark.asyncio` decorators.** `asyncio_mode = auto` is set in `pyproject.toml`. The markers are redundant noise.
15. **No duplicate test method names.** Python silently shadows the first definition. Each test method in a class must have a unique name.
16. **Mock ComfyUI responses with `respx`.** Use `@respx.mock` decorator and `respx.get/post().mock()` to simulate ComfyUI API responses. Never make real HTTP calls in tests.

### Adding a new tool (checklist)

1. Add the tool function in the appropriate `tools/*.py`
2. Use `@mcp.tool()` decorator with a clear docstring
3. Call `limiter.check("tool_name")` first
4. Call `audit.log(tool="tool_name", action="...")`
5. If it handles files: validate through `sanitizer`
6. If it submits workflows: inspect through `inspector`
7. Add the function to the `tool_fns` dict and return it
8. Wire it in `server.py` `_register_all_tools()` if it needs new dependencies
9. Add tests in `tests/test_tools_*.py` that call the function directly
10. Update the Tools table in `README.md`

### Adding a new client method (checklist)

1. Verify the ComfyUI endpoint is not on the blocked list (see rule 1)
2. Add the method to `ComfyUIClient` in `client.py`
3. Use `self._request(method, path, ...)` — this handles retries on connection errors
4. Add a test in `test_client.py` with `@respx.mock`

### Adding a new security check

1. Add to the appropriate module in `security/`
2. Wire it in `server.py` `_build_server()` and pass to tool registration
3. Add config fields to `config.py` if needed — every field must be read somewhere
4. Add tests in `tests/test_*.py`

### Maintaining the dangerous nodes list

The `_DEFAULT_DANGEROUS_NODES` list in `config.py` contains real ComfyUI custom node `class_type` values grouped by threat category (code execution, network access, filesystem access). To audit a new custom node package:

1. Check the package source for calls to `exec`, `eval`, `subprocess`, `os.system`, `open()`, `requests`, `urllib`, or `httpx`
2. Look for nodes that accept arbitrary file paths, URLs, or code as input
3. Add confirmed dangerous nodes to the appropriate category in `_DEFAULT_DANGEROUS_NODES` with a comment noting the source package and reason
4. If the node follows a naming pattern not yet covered, add a regex to `_DANGEROUS_NAME_PATTERNS` in `node_auditor.py`
5. Add tests for any new patterns

## Configuration

Config file: `~/.comfyui-mcp/config.yaml`

Key settings:
- `comfyui.url` — ComfyUI server URL
- `security.mode` — "audit" (log only) or "enforce" (block unapproved nodes)
- `security.dangerous_nodes` — List of node types to flag/warn
- `rate_limits.*` — Requests per minute per category

Environment variables override config: `COMFYUI_URL`, `COMFYUI_SECURITY_MODE`, etc.

## Testing Notes

- Uses `pytest-asyncio` with `asyncio_mode = auto`
- Mock ComfyUI API responses with `respx`
- Tests mirror `src/comfyui_mcp/` structure

## ComfyUI-Model-Manager API notes

The [ComfyUI-Model-Manager](https://github.com/hayden-fr/ComfyUI-Model-Manager) plugin wraps all its responses in a `{"success": bool, "data": <payload>}` envelope. The MCP client normalizes this in `_unwrap_model_manager_response()` before returning data to callers. All `respx` mocks for Model Manager endpoints must use this shape.

Two known quirks discovered against the live API:

1. **`previewFile` is always required** — `POST /model-manager/model` calls `save_model_preview()` server-side regardless. Omitting the field causes the task to be silently deleted with a misleading "Task not found" error. The client always sends `previewFile` (empty string is fine).
2. **Completed tasks stay as `pause`** — After a download finishes, the task remains in the list with `status: "pause"` and `progress: 100`. This is upstream behavior. Use `cancel_download` (which calls `DELETE /model-manager/download/{task_id}`) to remove it.
