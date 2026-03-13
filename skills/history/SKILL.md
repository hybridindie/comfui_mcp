---
description: Show recent ComfyUI generation history
---

# Generation History

Show recent ComfyUI completions.

Call `get_history` and format the results as a table or list showing:

- **Prompt ID**: the unique job identifier
- **Status**: whether it completed successfully or failed
- **Outputs**: filenames of generated images (if any)

Show the most recent entries first. If the user wants to view a specific output, they can use `get_image` with the filename.
