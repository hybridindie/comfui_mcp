# Project Guidelines

## Build And Test

- Use `uv` for all Python tasks.
- Core commands:
  - `uv sync`
  - `uv run pytest -v`
  - `uv run ruff check src/ tests/`
  - `uv run ruff format --check src/ tests/`
  - `uv run mypy src/comfyui_mcp/`
- Before finishing substantial changes, run relevant tests plus lint/format/type checks for touched files.

## Architecture

- Entry point is `src/comfyui_mcp/server.py`; `_build_server()` builds dependencies once and returns `(FastMCP, Settings)`.
- HTTP API access is centralized in `src/comfyui_mcp/client.py`.
- Security modules are under `src/comfyui_mcp/security/`; tools are under `src/comfyui_mcp/tools/`; workflow helpers are under `src/comfyui_mcp/workflow/`.
- Keep tool behavior in tool modules and transport/API details in `client.py`.

## Security-Critical Rules

- Never expose blocked ComfyUI endpoints: `/userdata`, `/free`, `/users`, `/history` POST delete, `/system_stats`.
- Every tool must:
  - call `limiter.check("tool_name")` first,
  - call `audit.log(...)`,
  - sanitize file inputs with `PathSanitizer` when filenames/subfolders are accepted.
- Any path that submits workflows via `client.post_prompt()` must run `inspector.inspect()` first and surface warnings.

## Testing Conventions

- Use `respx` to mock ComfyUI API calls; do not make real HTTP calls in tests.
- With `pytest-asyncio` auto mode, do not add `@pytest.mark.asyncio`.
- Test tools by calling functions returned from `register_*_tools()`; do not use private SDK internals.
- Keep test method names unique within classes.

## Code Conventions

- Add type hints for new code and keep imports at top of file.
- Avoid dead code and duplicate tools.
- Keep dependencies intentional: do not add packages unless imported by `src/`.
- Keep commits logical (separate behavior fixes, scripts/tooling, and docs when practical).

## Model Manager Notes

- ComfyUI-Model-Manager wraps payloads as `{"success": bool, "data": ...}`; normalize response shape at the client boundary.
- `previewFile` must be sent on `POST /model-manager/model` (empty string is valid).
- Completed downloads may remain with `status: "pause"` and `progress: 100`; use `cancel_download` cleanup behavior accordingly.

## Key References

- `CLAUDE.md` for repository-specific rules and checklists.
- `README.md` for tool behavior and operator guidance.
- `.github/instructions/repo-workflow.instructions.md` for workflow/PR handling preferences.
