---
description: Show ComfyUI queue status with running and pending jobs
---

# Queue Status

Show the current ComfyUI queue status.

Call `get_queue` and format the response as:

- **Running jobs**: count and list of prompt IDs currently executing
- **Pending jobs**: count and list of prompt IDs waiting in queue

If both lists are empty, report that the queue is idle.
