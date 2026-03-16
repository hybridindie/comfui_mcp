---
description: Create a ComfyUI workflow from a template
---

# Create Workflow

Create and optionally run a ComfyUI workflow. Template or description: "$ARGUMENTS".

## Steps

1. **List available templates.** If no specific template was requested, call `list_workflows` to show the available built-in templates (txt2img, img2img, etc.) and let the user choose.

2. **Create the workflow.** Call `create_workflow` with the chosen template name and any parameters the user specified (as a JSON string). For example:
   ```
   create_workflow(template="txt2img", params='{"prompt": "a sunset", "width": 768}')
   ```

3. **Validate the workflow.** Call `validate_workflow` with the workflow JSON returned from step 2. Report any warnings or errors.

4. **Present the workflow.** Show a summary of what the workflow does (nodes, connections, key parameters). Offer the user two options:
   - **Run it** — call `run_workflow` with `wait=True`
   - **Modify it** — use `modify_workflow` to add/remove nodes or change parameters, then re-validate

## Notes

- Use `summarize_workflow` to get a readable overview of any workflow JSON.
- For simple text-to-image generation, `/comfy:gen` is faster.
