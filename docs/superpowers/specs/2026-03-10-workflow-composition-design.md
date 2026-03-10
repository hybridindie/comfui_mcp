# Workflow Composition Tools — Design Spec

## Overview

Add three tools for programmatic workflow construction: `create_workflow` (build from templates), `modify_workflow` (batch graph operations), and `validate_workflow` (structural + server + security checks). This addresses issue #1.

## Tools

### `create_workflow(template, params)`

Returns a fully wired, runnable workflow JSON from a named template.

- `template`: string — one of `txt2img`, `img2img`, `upscale`, `inpaint`, `txt2vid_animatediff`, `txt2vid_wan`
- `params`: optional JSON string of parameter overrides (prompt, model, steps, etc.)
- All params are optional with sensible defaults. Unknown params are ignored.
- Returns: workflow JSON string ready for `run_workflow` or `modify_workflow`.

#### Templates

| Template | Key Params | Core Nodes |
|----------|-----------|------------|
| `txt2img` | prompt, negative_prompt, width, height, steps, cfg, model | CheckpointLoader, EmptyLatentImage, 2x CLIPTextEncode, KSampler, VAEDecode, SaveImage |
| `img2img` | prompt, negative_prompt, denoise, steps, cfg, model | CheckpointLoader, LoadImage, 2x CLIPTextEncode, KSampler, VAEDecode, VAEEncode, SaveImage |
| `upscale` | model_name | LoadImage, UpscaleModelLoader, ImageUpscaleWithModel, SaveImage |
| `inpaint` | prompt, negative_prompt, denoise, steps, cfg, model | CheckpointLoader, LoadImage, LoadImageMask, 2x CLIPTextEncode, SetLatentNoiseMask, KSampler, VAEDecode, VAEEncode, SaveImage |
| `txt2vid_animatediff` | prompt, negative_prompt, width, height, steps, cfg, model, motion_module, frames | CheckpointLoader, EmptyLatentImage, 2x CLIPTextEncode, ADE_AnimateDiffLoaderWithContext, KSampler, VAEDecode, SaveAnimatedWEBP |
| `txt2vid_wan` | prompt, negative_prompt, width, height, steps, cfg | DownloadAndLoadWanModel, WanTextToVideo, SaveAnimatedWEBP (or standard Wan 2.x nodes) |

For img2vid variants, the AI starts from a vid template and uses `modify_workflow` to swap in image loaders.

### `modify_workflow(workflow, operations)`

Applies a batch of operations to an existing workflow JSON.

- `workflow`: JSON string of the workflow to modify
- `operations`: JSON string of an array of operation objects
- Operations execute sequentially. If any fails, the entire batch fails with no partial application.
- Returns: modified workflow JSON string.

#### Operations

| Operation | Fields | Description |
|-----------|--------|-------------|
| `add_node` | `class_type`, `inputs` (optional), `node_id` (optional) | Add a node. Auto-generates `node_id` as next integer if omitted. |
| `remove_node` | `node_id` | Remove a node and clean up dangling references in other nodes' inputs. |
| `set_input` | `node_id`, `input_name`, `value` | Set a scalar input value on a node. |
| `connect` | `from_node`, `from_output`, `to_node`, `to_input` | Connect a node's output slot to another node's input. |
| `disconnect` | `node_id`, `input_name` | Clear a connection on a node's input (set to None/remove). |

### `validate_workflow(workflow)`

Validates a workflow across three layers. Returns structured results.

- `workflow`: JSON string of the workflow to validate
- Returns: JSON with `valid`, `errors`, `warnings`, `node_count`, `pipeline`.

#### Validation Layers

1. **Structural (local):** Every node has `class_type` and `inputs`. All connection references point to existing nodes. No graph cycles.
2. **Server (best-effort):** Node `class_type`s are installed (via `get_object_info()`) and referenced models exist (via `get_models()`). If server is unreachable, this layer is skipped with a warning.
3. **Security (reuses WorkflowInspector):** Dangerous node detection, suspicious input patterns, enforce mode blocking.

## Module Structure

```
src/comfyui_mcp/workflow/
    __init__.py          # Empty
    templates.py         # Template dicts + create logic
    operations.py        # Batch operation execution
    validation.py        # Structural + server + security checks

src/comfyui_mcp/tools/
    workflow.py          # Tool registration (thin layer)
```

### What moves

- `_analyze_workflow`, `WorkflowAnalysis`, `_MODEL_LOADERS`, `_SAMPLER_NODE_TYPES`, `_INPUT_NODE_TYPES` move from `generation.py` to `workflow/validation.py`. They are workflow analysis utilities used by both validation and summarization.
- `generation.py` imports these from `workflow.validation` for `summarize_workflow`.
- `_DEFAULT_TXT2IMG`, `_build_txt2img_workflow`, `_format_summary` stay in `generation.py`.

### Wiring

In `server.py` `_register_all_tools()`:

```python
register_workflow_tools(server, client, audit, rate_limiters["read"], inspector)
```

Rate limiting: all three tools use `rate_limiters["read"]` (60/min) since they don't submit workflows.

### Security compliance

All three tools call `limiter.check()` and `audit.log()` per project rules. `validate_workflow` runs the inspector. Actual workflow submission still goes through `run_workflow` with its own rate limit and inspector call.

## Testing

Test file: `tests/test_tools_workflow.py`

- **Templates:** Each template returns valid workflow JSON with expected nodes/wiring. Params override defaults. Unknown params ignored. Invalid template raises ValueError.
- **Operations:** add_node (with/without explicit ID), remove_node (cleans dangling refs), set_input, connect, disconnect. Sequential ordering. Atomic failure (no partial application).
- **Validation:** Structural errors (missing class_type, broken connections, cycles). Server checks (missing nodes, missing models — mock endpoints). Security warnings. Graceful degradation when server unreachable.
- **Integration:** create → modify → validate round-trip. Create txt2img → add LoRA → connect → validate passes.

Tests should use `respx` mocks so no real HTTP calls are made.
