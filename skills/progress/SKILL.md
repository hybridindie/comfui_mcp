---
description: Show execution progress for a ComfyUI job
---

# Job Progress

Show progress for a specific ComfyUI job. Prompt ID: "$ARGUMENTS".

Call `get_progress` with the prompt_id from "$ARGUMENTS". Format the response showing:

- **Current node**: which node is executing
- **Progress**: step X of Y (percentage)
- **Status**: running, completed, or failed

If no prompt_id is provided, suggest the user check `/comfy:status` first to find active job IDs, or `/comfy:history` for recent completions.
