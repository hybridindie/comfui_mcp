---
name: comfyui-troubleshooting
description: Troubleshooting guide for ComfyUI MCP connection issues, model errors, workflow failures, and security warnings. Use when users encounter errors or unexpected behavior.
---

# ComfyUI Troubleshooting Guide

## Connection Failures

**Symptoms:** Tools return connection errors, timeouts, or "ComfyUI not reachable" messages.

**Checks:**
1. Is ComfyUI running? Check the ComfyUI terminal/logs for errors.
2. Is the URL correct? Verify `COMFYUI_URL` environment variable or `comfyui.url` in `~/.comfyui-mcp/config.yaml`. Default is `http://localhost:8188`.
3. Firewall/network: If ComfyUI runs on a remote machine, ensure port 8188 is accessible.
4. Use `get_system_info` to test basic connectivity.

## Model Not Found

**Symptoms:** `generate_image` or workflows fail with "model not found" errors.

**Checks:**
1. Run `list_models` with the correct folder type (e.g., "checkpoints", "loras") to see what's available.
2. Model filenames are case-sensitive and must include the extension (e.g., `v1-5-pruned-emaonly.safetensors`).
3. If the model isn't listed, it needs to be placed in the correct ComfyUI models directory.
4. If ComfyUI Model Manager is installed, use `search_models` and `download_model` to fetch models directly.
5. Run `list_model_folders` to see all valid folder types.

## Workflow Execution Failures

**Symptoms:** `run_workflow` or `generate_image` fails after submission.

**Checks:**
1. Run `validate_workflow` first to catch structural issues.
2. Check for missing custom nodes — `list_nodes` shows what's installed. If a workflow uses nodes that aren't installed, it will fail.
3. Check connections — a node output index must match what the node actually produces. Use `get_node_info` to verify.
4. Check `get_queue` to see if the job is stuck or if there's a queue backlog.
5. Check `get_progress` with the prompt_id to see which node failed.

## Queue Stuck / Job Not Completing

**Symptoms:** Jobs stay in "running" state indefinitely, or the queue doesn't process.

**Checks:**
1. Use `get_queue` to see the current state.
2. Use `interrupt` to stop the currently running job.
3. Use `clear_queue` to remove all pending jobs.
4. Check ComfyUI logs for out-of-memory (OOM) errors — large images or complex workflows can exhaust VRAM.

## Security Warnings

**Symptoms:** Tools return messages about "dangerous nodes" or security warnings.

**What they mean:**
- The MCP server inspects workflows for nodes known to execute arbitrary code, access the network, or read/write files.
- In **audit** mode (default): warnings are logged but execution proceeds.
- In **enforce** mode: workflows containing dangerous nodes are blocked.

**What to do:**
1. Review the flagged nodes. The warning lists which node types were detected and why.
2. If you trust the nodes, you can proceed (audit mode) or add them to an allowlist in config.
3. Use `audit_dangerous_nodes` to scan all installed nodes proactively.
4. Change mode in `~/.comfyui-mcp/config.yaml`: `security.mode: "audit"` or `"enforce"`.

## ComfyUI Manager Not Detected

**Symptoms:** `search_custom_nodes`, `install_custom_node`, and related tools fail or report Manager not available.

**Fix:** Install [ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager):
1. Navigate to `ComfyUI/custom_nodes/`
2. `git clone https://github.com/ltdrdata/ComfyUI-Manager.git`
3. Restart ComfyUI
4. Use `get_server_features` to verify detection.

## Model Manager Not Detected

**Symptoms:** `search_models`, `download_model` fail or report Model Manager not available.

**Fix:** Install [ComfyUI-Model-Manager](https://github.com/hayden-fr/ComfyUI-Model-Manager):
1. Navigate to `ComfyUI/custom_nodes/`
2. `git clone https://github.com/hayden-fr/ComfyUI-Model-Manager.git`
3. Restart ComfyUI
4. Use `get_server_features` to verify detection.
