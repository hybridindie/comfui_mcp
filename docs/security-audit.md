# Security Audit: ComfyUI MCP Server

**Audit Date:** 2026-03-03  
**Version:** 0.1.0

---

## Executive Summary

This document provides a comprehensive security audit of the ComfyUI MCP Server. The server implements multiple security layers to protect against malicious workflows, path traversal attacks, and denial of service attempts. The current security posture is **Strong** with some areas for improvement identified.

---

## Threat Model

### Assets to Protect
1. **ComfyUI Server** - Backend image generation service
2. **File System** - Input/output directories on ComfyUI host
3. **MCP Client** - AI assistant invoking the MCP
4. **Configuration** - Security settings and tokens

### Threat Actors
1. **Malicious AI Client** - Could attempt to execute dangerous workflows
2. **Compromised MCP Client** - Could inject malicious payloads
3. **Network Attacker** - MITM attacks on unencrypted connections

### Attack Vectors
1. **Arbitrary Code Execution** via dangerous workflow nodes
2. **Path Traversal** via file operation parameters
3. **Denial of Service** via resource exhaustion
4. **Information Disclosure** via audit logs or API responses

---

## Security Controls Implemented

### 1. Workflow Inspector ✅

**Purpose:** Detect and block malicious or dangerous ComfyUI workflows

**Mechanism:**
- Parses workflow JSON to extract node types
- Checks against configurable blocklist (`dangerous_nodes`)
- Pattern matching for suspicious code in inputs:
  - `__import__()`, `eval()`, `exec()`
  - `os.system()`, `subprocess`, file write operations
- Two modes: `audit` (log only) or `enforce` (block)

**Current Dangerous Nodes Blocked:**
```python
_DEFAULT_DANGEROUS_NODES = [
    "ExecuteAnything",
    "EvalNode", 
    "ExecNode",
    "PythonExec",
    "RunPython",
    "ShellNode",
    "CommandExecutor",
]
```

**Strengths:**
- ✅ Recursive input inspection for nested values
- ✅ Audit logging of all inspections
- ✅ Configurable allowlist/blocklist

**Limitations:**
- ⚠️ Blocklist is static; custom nodes with similar functionality may not be caught
- ⚠️ Pattern matching can be bypassed with obfuscation
- ⚠️ No inspection of node outputs

---

### 2. Path Sanitizer ✅

**Purpose:** Prevent path traversal and unauthorized file access

**Mechanism:**
- Validates filename and subfolder parameters
- Blocks: `..`, absolute paths, null bytes, special characters
- Validates file extensions against allowlist
- Enforces maximum upload size (default 50MB)
- Validates filename length (max 255 characters)
- Validates size is non-negative

**Validation Rules:**
```python
- Null bytes (\x00) → BLOCKED
- Absolute paths (/...) → BLOCKED  
- Path traversal (..) → BLOCKED
- Invalid extensions → BLOCKED
- Files exceeding size → BLOCKED
- Special chars in subfolder (\n, \r) → BLOCKED
- Filename too long (>255 chars) → BLOCKED
- Negative file size → BLOCKED
```

**Strengths:**
- ✅ Handles percent-encoded inputs (URL decoding)
- ✅ Separate validation for filename and subfolder
- ✅ Case-insensitive extension matching

---

### 3. Rate Limiter ✅

**Purpose:** Prevent denial of service via request flooding

**Mechanism:**
- Token-bucket algorithm per tool category
- Configurable requests per minute

**Default Limits:**
```yaml
rate_limits:
  workflow: 10      # run_workflow
  generation: 10    # generate_image
  file_ops: 30      # upload, download
  read_only: 60     # list, get
```

**Strengths:**
- ✅ Per-tool tracking
- ✅ Sliding window refill
- ✅ Graceful error messages

**Limitations:**
- ⚠️ In-memory only (resets on restart)
- ⚠️ No distributed rate limiting across instances
- ⚠️ No per-client isolation

---

### 4. Audit Logger ✅

**Purpose:** Comprehensive logging of all operations

**Logged Data:**
- Timestamp
- Tool name
- Action performed
- Prompt ID (when applicable)
- Node types used
- Warnings generated
- Execution duration

**Security Features:**
- Automatic redaction of sensitive fields:
  - `token`, `password`, `secret`, `api_key`, `authorization`
- JSON Lines format for easy parsing
- Configurable output file
- Graceful error handling (logs to stderr on failure)

---

### 5. Blocked Endpoints ⚠️

**Not Exposed (Security Decision):**
| Endpoint | Reason |
|----------|--------|
| `/system_stats` | Information disclosure (GPU memory, Python version) |
| `/userdata/*` | Arbitrary file read/write |
| `/free` | DoS vector (unload models) |
| `/users` | User management (not needed) |

**Strengths:**
- ✅ Deliberate exclusion from client implementation

**Limitations:**
- ⚠️ No enforcement at network level - relies on client not exposing these

---

## Security Analysis by Component

### HTTP Client (`client.py`)

| Security Control | Status | Notes |
|-----------------|--------|-------|
| TLS Support | ✅ | Configurable `tls_verify` |
| Connection Pooling | ✅ | Reuses connections |
| Timeout Configuration | ✅ | Connect & read timeouts |
| Certificate Validation | ✅ | Configurable |
| Retry Logic | ✅ | Exponential backoff for 5xx errors |
| Request Retries | ✅ | 3 retries by default, configurable |

**Potential Issues:**
- ⚠️ No request signing

---

### Configuration (`config.py`)

| Security Control | Status | Notes |
|-----------------|--------|-------|
| YAML Safe Load | ✅ | Uses `yaml.safe_load` |
| Env Var Overrides | ✅ | Limited to specific vars |
| Type Validation | ✅ | Pydantic validation |
| Default Values | ✅ | Secure defaults |
| URL Validation | ✅ | Validates scheme and host |
| Max Length Limits | ✅ | Bounds validation on numeric fields |

---

## Risk Assessment

### High Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-------------|
| Arbitrary code execution via workflow | Medium | Critical | Workflow inspector + enforce mode |
| Path traversal attack | Low | High | Path sanitizer |

### Medium Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-------------|
| DoS via large file upload | Medium | Medium | Size limits + rate limiting |
| DoS via rapid requests | Medium | Medium | Rate limiter |
| Credential leakage in logs | Low | Medium | Redaction implemented |

### Low Risk

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|-------------|
| Information disclosure | Low | Low | Blocked sensitive endpoints |
| MITM attack | Low | Medium | TLS verification available |

---

## Recommendations

### Production Deployment

For production deployments, run the MCP server behind a reverse proxy (nginx, Traefik, etc.) to add:

- CSP headers for SSE transport
- TLS termination
- Additional authentication

Example nginx config snippet:
```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    add_header Content-Security-Policy "default-src 'self'; connect-src 'self' http://127.0.0.1:8080;";
}
```

---

## Compliance Notes

- **No PII** is collected or stored
- **Tokens** are redacted from logs
- **No external telemetry** 
- **Local-only** by design (connects to specified ComfyUI instance)
