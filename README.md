# comfyui-mcp

A secure MCP (Model Context Protocol) server for [ComfyUI](https://github.com/comfyanonymous/ComfyUI). Enables AI assistants like Claude to generate images, run workflows, and manage jobs through ComfyUI — with built-in security controls that existing ComfyUI MCP servers lack.

## Why this exists

Every existing ComfyUI MCP server is a thin passthrough to ComfyUI's API with no security guardrails. They allow arbitrary workflow execution (including malicious custom nodes that run `eval`/`exec`), have no input validation, no file path sanitization, no rate limiting, and no audit trail.

This server adds five security layers between the AI assistant and ComfyUI:

| Layer | What it does |
|-------|-------------|
| **Workflow Inspector** | Parses every workflow before execution, extracts node types, flags dangerous patterns (`eval`, `exec`, `__import__`, `subprocess`). Configurable audit-only or enforcement mode. |
| **Path Sanitizer** | Validates all filenames — blocks path traversal (`../`), null bytes, percent-encoded attacks, absolute paths, and disallowed file extensions. |
| **Rate Limiter** | Token-bucket rate limiting per tool category to prevent runaway loops. |
| **Audit Logger** | Structured JSON logging of every operation with automatic redaction of sensitive fields (tokens, passwords). |
| **Selective API Surface** | Only exposes safe ComfyUI endpoints. Dangerous endpoints (`/userdata`, `/free`, `/users`, `/system_stats`) are never proxied. |

## Quick start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A running ComfyUI instance (local or remote)

### Install

```bash
git clone https://github.com/yourusername/comfyui-mcp.git
cd comfyui-mcp
uv sync
```

### Configure

Create a minimal config for your ComfyUI instance:

```bash
mkdir -p ~/.comfyui-mcp
cat > ~/.comfyui-mcp/config.yaml << 'EOF'
comfyui:
  url: "http://127.0.0.1:8188"
EOF
```

For a remote server:

```bash
cat > ~/.comfyui-mcp/config.yaml << 'EOF'
comfyui:
  url: "https://your-gpu-server:8188"
EOF
```

### Add to Claude Code

Add to your Claude Code MCP configuration (`~/.claude/claude_desktop_config.json` or equivalent):

```json
{
  "mcpServers": {
    "comfyui": {
      "command": "uv",
      "args": ["--directory", "/path/to/comfyui-mcp", "run", "comfyui-mcp"]
    }
  }
}
```

### Verify

```bash
# Check server starts and lists tools
uv run python -c "from comfyui_mcp.server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
```

## Tools

### Generation & Workflows

| Tool | Description |
|------|-------------|
| `generate_image` | Text-to-image using a built-in workflow. Params: prompt, negative_prompt, width, height, steps, cfg, model. |
| `run_workflow` | Submit arbitrary ComfyUI workflow JSON. Inspected for dangerous nodes before execution. |

### Job Management

| Tool | Description |
|------|-------------|
| `get_queue` | Get current execution queue state. |
| `get_job` | Check status of a job by prompt_id. |
| `cancel_job` | Cancel a running or queued job. |
| `interrupt` | Interrupt the currently executing workflow. |

### Discovery

| Tool | Description |
|------|-------------|
| `list_models` | List available models by folder (checkpoints, loras, vae, etc.). |
| `list_nodes` | List all available node types. |
| `get_node_info` | Get detailed info about a specific node type. |
| `list_workflows` | List saved workflow templates. |

### History

| Tool | Description |
|------|-------------|
| `get_history` | Browse execution history (read-only). |
| `get_history_item` | Get details of a specific history entry. |

### File Operations

| Tool | Description |
|------|-------------|
| `upload_image` | Upload a base64-encoded image to ComfyUI's input directory. Path-sanitized. |
| `get_image` | Download a generated image. Returns base64-encoded data URI. Path-sanitized. |
| `list_outputs` | List generated output filenames from history. |

### Deliberately not exposed

These ComfyUI endpoints are **never** proxied due to security risks:

- `/userdata` — arbitrary file read/write
- `/free` — unload models (DoS vector)
- `/users` — user management
- `/history` POST — delete history
- `/system_stats` — unnecessary information disclosure

## Configuration

Config file: `~/.comfyui-mcp/config.yaml`

```yaml
comfyui:
  url: "http://127.0.0.1:8188"   # ComfyUI server URL
  tls_verify: true                 # TLS certificate verification
  timeout_connect: 30              # Connection timeout (seconds)
  timeout_read: 300                # Read timeout (seconds)

security:
  mode: "audit"                    # "audit" (log only) or "enforce" (block unapproved)
  allowed_nodes: []                # Enforce mode: only these nodes can run
  dangerous_nodes:                 # Always flagged in audit log
    - "ExecuteAnything"
    - "EvalNode"
    - "ExecNode"
    - "PythonExec"
    - "RunPython"
    - "ShellNode"
    - "CommandExecutor"
  max_upload_size_mb: 50
  allowed_extensions:
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".webp"
    - ".gif"
    - ".json"

rate_limits:                       # Requests per minute
  workflow: 10
  generation: 10
  file_ops: 30
  read_only: 60

logging:
  level: "INFO"
  audit_file: "~/.comfyui-mcp/audit.log"

transport:
  stdio: true
  sse:
    enabled: false
    host: "127.0.0.1"
    port: 8080
```

### Environment variables

Environment variables override config file values:

| Variable | Overrides |
|----------|-----------|
| `COMFYUI_URL` | `comfyui.url` |
| `COMFYUI_TLS_VERIFY` | `comfyui.tls_verify` |
| `COMFYUI_LOG_LEVEL` | `logging.level` |

## Security modes

### Audit mode (default)

Every workflow is inspected and logged, but nothing is blocked. Use this during development to understand what nodes your workflows use.

```yaml
security:
  mode: "audit"
```

Audit log entries look like:

```json
{
  "timestamp": "2026-02-25T14:30:00+00:00",
  "tool": "run_workflow",
  "action": "inspected",
  "nodes_used": ["KSampler", "CLIPTextEncode", "VAEDecode", "SaveImage"],
  "warnings": []
}
```

When a dangerous node is detected, warnings are included in the tool response:

```
Workflow submitted. prompt_id: abc123

⚠️ Warnings detected:
  - Dangerous node type: ExecutePython
  - Suspicious input in node 5 (ExecutePython), field 'code'
```

The MCP instructions tell the LLM to inform users and ask for confirmation before proceeding when warnings are present.

### Building your dangerous node list

Use the `audit_dangerous_nodes` tool to scan your ComfyUI installation for potentially dangerous nodes:

| Tool | Description |
|------|-------------|
| `audit_dangerous_nodes` | Scans all installed nodes and returns dangerous/suspicious ones with reasons |

Run this once to see what dangerous nodes are installed:

```
audit_dangerous_nodes() → {
  "total_nodes": 456,
  "dangerous": {
    "count": 12,
    "nodes": [
      {"class": "ExecutePython", "reason": "Name matches pattern: \\bexec\\b"},
      {"class": "RunPython", "reason": "Name matches pattern: \\brunpython\\b"},
      {"class": "ShellCommand", "reason": "Name matches pattern: \\bshell\\b"}
    ]
  },
  "suspicious": {...}
}
```

Add these to your config:

```yaml
security:
  mode: "audit"
  dangerous_nodes:
    - "ExecutePython"      # from audit_dangerous_nodes
    - "RunPython"
    - "ShellCommand"
    # ... other nodes found by audit
```

### Enforce mode

Only explicitly approved nodes can run. Any workflow containing an unapproved node is rejected.

```yaml
security:
  mode: "enforce"
  allowed_nodes:
    - "KSampler"
    - "CheckpointLoaderSimple"
    - "CLIPTextEncode"
    - "VAEDecode"
    - "EmptyLatentImage"
    - "SaveImage"
    - "LoadImage"
    - "LoraLoader"
```

**Tip:** Use `audit_dangerous_nodes` to identify dangerous nodes, run workflows in audit mode to see which nodes you use, then switch to enforce mode with that allowlist.

## Audit log

All tool invocations are logged as JSON lines to `~/.comfyui-mcp/audit.log`:

```bash
# Watch the audit log in real time
tail -f ~/.comfyui-mcp/audit.log | python -m json.tool

# Find all workflows that used dangerous nodes
grep '"warnings":\[' ~/.comfyui-mcp/audit.log | grep -v '"warnings":\[\]'
```

Sensitive fields (`token`, `password`, `secret`, `api_key`, `authorization`) are automatically redacted from log entries.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LLM (Claude, etc.)                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │ MCP
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ComfyUI MCP Server                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Config    │  │   Audit     │  │   Security Layers       │  │
│  │  (YAML/env) │  │   Logger    │  │  ┌───────────────────┐  │  │
│  └─────────────┘  └─────────────┘  │  │ Workflow Inspector│  │  │
│                                     │  │ - Dangerous nodes │  │  │
│                                     │  │ - Suspicious input│  │  │
│                                     │  ├───────────────────┤  │  │
│                                     │  │  Path Sanitizer   │  │  │
│                                     │  │ - Traversal block │  │  │
│                                     │  │ - Extension filter│  │  │
│                                     │  ├───────────────────┤  │  │
│                                     │  │  Rate Limiter     │  │  │
│                                     │  │  (token-bucket)   │  │  │
│                                     │  └───────────────────┘  │  │
│                                     └─────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Tool Groups                               │ │
│  │  generation.py | jobs.py | discovery.py | history.py | files.py│
│  └─────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬─────────────────────────────────┘
                                │ httpx
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ComfyUI Server                               │
│              (REST API - port 8188)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | File | Responsibility |
|-----------|------|----------------|
| Server | `server.py` | Entry point, wires components, registers tools |
| Config | `config.py` | Pydantic settings, YAML loading, env overrides |
| Client | `client.py` | Async HTTP client for ComfyUI REST API |
| Audit | `audit.py` | Structured JSON logging with redaction |
| Workflow Inspector | `security/inspector.py` | Node type detection, dangerous pattern matching |
| Path Sanitizer | `security/sanitizer.py` | Path traversal, extension filtering |
| Rate Limiter | `security/rate_limit.py` | Token-bucket per tool category |

### Tool registration pattern

Each `tools/*.py` module exports `register_*_tools(server, client, audit, limiter, ...)` which:
1. Defines `@server.tool()` decorated async functions
2. Checks rate limits
3. Logs audit events
4. Returns results to the LLM

## Development

### Run tests

```bash
uv sync
uv run pytest -v
```

### Project structure

```
src/comfyui_mcp/
├── server.py              # MCP server entry point, wires all components
├── config.py              # Pydantic settings, YAML loading, env overrides
├── client.py              # Async HTTP client for ComfyUI API
├── audit.py               # Structured JSON audit logger
├── security/
│   ├── inspector.py       # Workflow node inspection (audit/enforce)
│   ├── sanitizer.py       # File path validation
│   └── rate_limit.py      # Token-bucket rate limiter
└── tools/
    ├── generation.py      # generate_image, run_workflow
    ├── jobs.py            # get_queue, get_job, cancel_job, interrupt
    ├── discovery.py       # list_models, list_nodes, get_node_info, list_workflows
    ├── history.py         # get_history, get_history_item
    └── files.py           # upload_image, get_image, list_outputs
```

## License

MIT
