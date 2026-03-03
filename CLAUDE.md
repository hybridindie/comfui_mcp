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
- **Validation**: pydantic, pydantic-settings
- **Logging**: structlog
- **Config**: pyyaml

## Project Structure

```
src/comfyui_mcp/
├── server.py              # MCP server entry, wires all components
├── config.py              # Pydantic settings, YAML loading, env overrides
├── client.py              # Async HTTP client for ComfyUI API
├── audit.py               # Structured JSON audit logger
├── security/
│   ├── inspector.py       # Workflow node inspection (audit/enforce)
│   ├── sanitizer.py      # File path validation
│   └── rate_limit.py      # Token-bucket rate limiter
└── tools/
    ├── generation.py      # generate_image, run_workflow
    ├── jobs.py            # get_queue, get_job, cancel_job, interrupt
    ├── discovery.py        # list_models, list_nodes, get_node_info, list_workflows
    ├── history.py         # get_history, get_history_item
    └── files.py           # upload_image, get_image, list_outputs

tests/                     # pytest with asyncio_mode = auto
docs/plans/               # Design documents
pyproject.toml            # Project config (hatchling build)
```

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_server.py -v

# Run with coverage
uv run pytest --cov=src/comfyui_mcp --cov-report=term-missing

# Type check (if mypy configured)
uv run mypy src/comfyui_mcp

# Lint (if ruff configured)
uv run ruff check src/
```

## Configuration

Config file: `~/.comfyui-mcp/config.yaml`

Key settings:
- `comfyui.url` — ComfyUI server URL
- `security.mode` — "audit" (log only) or "enforce" (block unapproved nodes)
- `security.dangerous_nodes` — List of node types to flag/warn
- `rate_limits.*` — Requests per minute per category

Environment variables override config: `COMFYUI_URL`, `COMFYUI_SECURITY_MODE`, etc.

## Code Conventions

- **No comments** unless explicitly requested
- **Async everything** — use `async def`, `await`, `httpx.AsyncClient`
- **Pydantic models** for all config and data structures
- **Structured logging** via structlog
- **Type hints** throughout
- **Tool registration pattern**: Each `tools/*.py` has `register_*_tools(server, client, audit, limiter)` function
- **Audit logging**: Every tool call should log via `audit.log()` with structured JSON

## Common Development Tasks

### Adding a new tool
1. Add tool function to appropriate `tools/*.py`
2. Use `@server.tool()` decorator
3. Add rate limiter parameter from registration
4. Log via `audit.log(tool="...", action="...", ...)`
5. Add test in `tests/test_tools_*.py`

### Adding a new security check
1. Add to appropriate module in `security/`
2. Integrate in `server.py` `_build_server()` function
3. Add configuration to `config.py` if needed
4. Add tests in `tests/test_*.py`

### Running against a local ComfyUI
```bash
export COMFYUI_URL="http://127.0.0.1:8188"
uv run comfyui-mcp
```

## Testing Notes

- Uses `pytest-asyncio` with `asyncio_mode = auto`
- Mock ComfyUI API responses with `respx` (see existing tests)
- Fixtures in `tests/conftest.py`
- Tests mirror `src/comfyui_mcp/` structure
