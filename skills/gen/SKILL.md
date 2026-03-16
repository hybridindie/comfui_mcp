---
description: Generate an image with ComfyUI from a text prompt
---

# Generate Image

Generate an image using ComfyUI based on the user's prompt "$ARGUMENTS".

## Steps

1. **Parse the prompt.** Extract any explicit parameters (dimensions, steps, cfg, model name) from the user's request. Use these defaults for anything not specified:
   - width: 512, height: 512
   - steps: 20
   - cfg: 7.0
   - negative_prompt: "bad quality, blurry"

2. **Select a model.** If the user didn't specify a model, call `list_models` with folder `"checkpoints"` and suggest one from the results. Ask the user to confirm before proceeding, or let them pick a different one.

3. **Generate the image.** Call `generate_image` with the parsed parameters and `wait=True` so we block until completion.

4. **Fetch the result.** Once generation completes, the response includes the output filename. Call `get_image` with that filename and subfolder `"output"` to retrieve it.

5. **Present the result.** Show the image and a summary of the generation parameters used (prompt, model, dimensions, steps, cfg).

## Notes

- If generation fails, check `get_queue` to see if ComfyUI is busy or stuck.
- For img2img, ControlNet, or other advanced workflows, use `/comfy:workflow` instead.
