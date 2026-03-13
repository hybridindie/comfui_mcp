# Contributing to comfyui-mcp

Thanks for your interest in contributing!

## Development

```bash
# Clone and setup
git clone https://github.com/hybridindie/comfyui-mcp.git
cd comfyui-mcp
uv sync

# Install git hooks (required — do this once after cloning)
uv run pre-commit install

# Run tests
uv run pytest -v

# Run tests with coverage
uv run pytest --cov=src/comfyui_mcp --cov-report=term-missing

# Run with local ComfyUI
export COMFYUI_URL="http://127.0.0.1:8188"

# Optional for model search/download against authenticated resources
export COMFYUI_HUGGINGFACE_TOKEN="hf_xxx"
export COMFYUI_CIVITAI_API_KEY="xxx"

uv run comfyui-mcp
```

## Pre-commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to enforce code quality via a git hook. After running `uv run pre-commit install`, the following checks run automatically on every `git commit` against your staged files:

- **Trailing whitespace** and **end-of-file fixer** — auto-fixes whitespace issues
- **YAML check** — validates YAML syntax
- **Large file check** — prevents accidental commits of large files
- **Ruff lint** — catches bugs, security issues, and style violations (auto-fixes where possible)
- **Ruff format** — enforces consistent code formatting
- **Mypy** — checks type annotations

If a hook auto-fixes a file, re-stage the changes and commit again. If it reports an error, fix it manually before committing.

You can also run individual tools directly if needed:

```bash
uv run ruff check src/ tests/        # Lint
uv run ruff format src/ tests/       # Format (in-place)
uv run mypy src/comfyui_mcp/         # Type check
```

## Testing

All changes must include tests. Tests use `pytest` with `pytest-asyncio` (auto mode) and `respx` for mocking HTTP calls.

```bash
# Run all tests
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_client.py -v

# Run with coverage
uv run pytest --cov=src/comfyui_mcp --cov-report=term-missing
```

Key testing rules:
- Call actual tool functions via the dicts returned by `register_*_tools()`
- Mock ComfyUI API responses with `respx` — never make real HTTP calls
- No `@pytest.mark.asyncio` decorators (auto mode handles this)
- No duplicate test method names within a class

## Code Style

- Async everything — use `async def`, `await`, `httpx.AsyncClient`
- Pydantic models for config and data structures
- Type hints throughout
- All code must pass `ruff check`, `ruff format --check`, and `mypy`

## Security

This project handles workflow execution against ComfyUI. When adding features:

1. **Never expose dangerous ComfyUI endpoints** (`/userdata`, `/free`, `/users`, `/history` POST)
2. **Validate all inputs** — use Pydantic models
3. **Log audit events** for every tool call
4. **Sanitize file paths** if handling filenames

## Adding a New Tool

1. Add tool function to appropriate `tools/*.py`
2. Use `@mcp.tool()` decorator
3. Add rate limiter check
4. Log via `audit.log()` with structured JSON
5. Add test in `tests/`

## Submitting PRs

1. Fork the repo
2. Create a feature branch
3. Make changes with tests
4. Ensure tests pass: `uv run pytest -v`
5. Commit — the git hook will run lint, format, and type checks automatically
6. Push and open a PR

CI will run lint, type-check, and test jobs automatically on your PR.
