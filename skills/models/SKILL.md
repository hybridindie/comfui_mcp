---
description: List available ComfyUI models, optionally filtered by type
---

# List Models

List models available in ComfyUI. Filter type: "$ARGUMENTS".

Call `list_models` with the folder argument. If "$ARGUMENTS" is provided, use it as the folder type (e.g., "checkpoints", "loras", "vae", "controlnet", "upscale_models"). If no argument is given, default to `"checkpoints"`.

Format the results as a clean list of model filenames. If the list is long, group by subfolder if applicable.

To see all available model folder types, call `list_model_folders`.
