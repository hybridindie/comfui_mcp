# Contributing to comfyui-mcp

Thanks for your interest in contributing!

## Development

```bash
# Clone and setup
git clone https://github.com/hybridindie/comfyui-mcp.git
cd comfyui-mcp
uv sync

# Run tests
uv run pytest -v

# Run with local ComfyUI
export COMFYUI_URL="http://127.0.0.1:8188"
uv run comfyui-mcp
```

## Code Style

- No comments unless explicitly requested
- Async everything — use `async def`, `await`, `httpx.AsyncClient`
- Pydantic models for config and data structures
- Type hints throughout
- Structured logging via structlog

## Security

This project handles workflow execution against ComfyUI. When adding features:

1. **Never expose dangerous ComfyUI endpoints** (`/userdata`, `/free`, `/users`, `/history` POST)
2. **Validate all inputs** — use Pydantic models
3. **Log audit events** for every tool call
4. **Sanitize file paths** if handling filenames

## Adding a New Tool

1. Add tool function to appropriate `tools/*.py`
2. Use `@server.tool()` decorator
3. Add rate limiter check
4. Log via `audit.log()` with structured JSON
5. Add test in `tests/`

## Submitting PRs

1. Fork the repo
2. Create a feature branch
3. Make changes with tests
4. Run `uv run ruff check src/` and `uv run pytest`
5. Push and open a PR