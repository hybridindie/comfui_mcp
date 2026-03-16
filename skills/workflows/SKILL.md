---
name: comfyui-workflows
description: Knowledge about ComfyUI workflow API format, node connections, and common patterns. Use when helping users build, modify, or understand workflows.
---

# ComfyUI Workflow Building Guide

## API Format

ComfyUI workflows use a JSON format where each node is a key-value pair:

```json
{
  "1": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 42,
      "steps": 20,
      "cfg": 7.0,
      "sampler_name": "euler",
      "scheduler": "normal",
      "denoise": 1.0,
      "model": ["2", 0],
      "positive": ["3", 0],
      "negative": ["4", 0],
      "latent_image": ["5", 0]
    }
  }
}
```

- **Keys** are string node IDs (e.g., `"1"`, `"2"`)
- **`class_type`** is the ComfyUI node type name
- **`inputs`** contains parameters and connections
- **Connections** use the format `["source_node_id", output_index]`

## Common Node Chains

### txt2img (text to image)
`CheckpointLoaderSimple` -> `CLIPTextEncode` (positive) -> `KSampler` -> `VAEDecode` -> `SaveImage`

### img2img (image to image)
`LoadImage` -> `VAEEncode` -> `KSampler` (with denoise < 1.0) -> `VAEDecode` -> `SaveImage`

### ControlNet
`LoadImage` -> `ControlNetLoader` + `ControlNetApply` -> feed into `KSampler` positive conditioning

### LoRA Stacking
`CheckpointLoaderSimple` -> `LoraLoader` (chain multiple) -> `KSampler`

## Key Nodes Reference

| Node | Purpose | Key Inputs |
|------|---------|------------|
| `CheckpointLoaderSimple` | Load a model checkpoint | `ckpt_name` |
| `CLIPTextEncode` | Encode text prompt | `text`, `clip` |
| `KSampler` | Run diffusion sampling | `model`, `positive`, `negative`, `latent_image`, `steps`, `cfg`, `seed` |
| `VAEDecode` | Decode latent to image | `samples`, `vae` |
| `VAEEncode` | Encode image to latent | `pixels`, `vae` |
| `SaveImage` | Save output image | `images`, `filename_prefix` |
| `LoadImage` | Load input image | `image` (filename) |
| `LoraLoader` | Apply LoRA weights | `model`, `clip`, `lora_name`, `strength_model`, `strength_clip` |
| `ControlNetLoader` | Load ControlNet model | `control_net_name` |
| `ControlNetApply` | Apply ControlNet | `conditioning`, `control_net`, `image`, `strength` |

## Using the Workflow Tools

1. **`create_workflow`** — Start from a template. Available templates can be listed with `list_workflows`.
2. **`modify_workflow`** — Add/remove nodes, change connections, update parameters on an existing workflow.
3. **`validate_workflow`** — Check for missing connections, unknown node types, and potential issues.
4. **`summarize_workflow`** — Get a human-readable description of what a workflow does.
5. **`run_workflow`** — Submit a workflow for execution. Use `wait=True` to block until done.

## Tips

- Always validate a workflow before running it.
- Use `list_nodes` to check what node types are available on the connected ComfyUI instance.
- Use `get_node_info` to get detailed input/output specs for a specific node type.
- Node IDs must be unique strings. When adding nodes, pick IDs that don't conflict with existing ones.
- The `seed` parameter controls reproducibility. Use a fixed seed for consistent results, or -1 for random.
