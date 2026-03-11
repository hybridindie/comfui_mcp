"""WebSocket progress tracking for ComfyUI workflow execution."""

from __future__ import annotations

import asyncio
import contextlib
import json
import ssl
import time
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets

from comfyui_mcp.client import ComfyUIClient


@dataclass
class ProgressState:
    """Unified progress state for a workflow execution."""

    prompt_id: str
    status: str = "unknown"
    queue_position: int | None = None
    current_node: str | None = None
    step: int | None = None
    total_steps: int | None = None
    elapsed_seconds: float | None = None
    outputs: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, omitting None fields."""
        d: dict[str, Any] = {"prompt_id": self.prompt_id, "status": self.status}
        if self.queue_position is not None:
            d["queue_position"] = self.queue_position
        if self.current_node is not None:
            d["current_node"] = self.current_node
        if self.step is not None:
            d["step"] = self.step
        if self.total_steps is not None:
            d["total_steps"] = self.total_steps
        if self.elapsed_seconds is not None:
            d["elapsed_seconds"] = self.elapsed_seconds
        if self.outputs:
            d["outputs"] = self.outputs
        return d


class WebSocketProgress:
    """Manages on-demand WebSocket connections for progress tracking."""

    def __init__(
        self, client: ComfyUIClient, timeout: float = 300.0, tls_verify: bool = True
    ) -> None:
        self._client = client
        self._timeout = timeout
        self._tls_verify = tls_verify
        self._client_id = uuid.uuid4().hex

    def _ws_url(self) -> str:
        """Derive WebSocket URL from client's HTTP base URL."""
        parsed = urlparse(self._client.base_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{ws_scheme}://{parsed.netloc}/ws?clientId={self._client_id}"

    async def wait_for_completion(self, prompt_id: str) -> ProgressState:
        """Connect via WebSocket and block until the prompt completes, errors, or times out."""
        state = ProgressState(prompt_id=prompt_id, status="running")
        start_time = time.monotonic()

        try:
            ws_kwargs: dict[str, Any] = {}
            if self._ws_url().startswith("wss://") and not self._tls_verify:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ws_kwargs["ssl"] = ctx

            async with asyncio.timeout(self._timeout):
                async with websockets.connect(self._ws_url(), **ws_kwargs) as ws:
                    async for raw_msg in ws:
                        if isinstance(raw_msg, bytes):
                            continue
                        msg = json.loads(raw_msg)
                        msg_type = msg.get("type")
                        data = msg.get("data", {})

                        # Filter events by prompt_id — ComfyUI sends
                        # events for all jobs on the same connection
                        event_prompt_id = data.get("prompt_id")
                        if event_prompt_id is not None and event_prompt_id != prompt_id:
                            continue

                        if msg_type == "progress":
                            state.step = data.get("value")
                            state.total_steps = data.get("max")

                        elif msg_type == "executing":
                            node = data.get("node")
                            if node is None:
                                # null node means execution finished
                                state.status = "completed"
                                break
                            state.current_node = node

                        elif msg_type == "executed":
                            output = data.get("output", {})
                            for key in ("images", "gifs"):
                                for item in output.get(key, []):
                                    state.outputs.append(
                                        {
                                            "node_id": data.get("node", ""),
                                            "filename": item.get("filename", ""),
                                            "subfolder": item.get("subfolder", ""),
                                        }
                                    )

                        elif msg_type == "execution_error":
                            state.status = "error"
                            break

        except TimeoutError:
            state.status = "timeout"
        except (OSError, websockets.exceptions.WebSocketException):
            # WebSocket failed — fall back to HTTP polling per spec
            return await self._poll_until_complete(prompt_id, start_time)

        state.elapsed_seconds = round(time.monotonic() - start_time, 2)
        return state

    async def _poll_until_complete(self, prompt_id: str, start_time: float) -> ProgressState:
        """Poll HTTP endpoints until completion or timeout."""
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= self._timeout:
                state = ProgressState(prompt_id=prompt_id, status="timeout")
                state.elapsed_seconds = round(elapsed, 2)
                return state
            state = await self.get_state(prompt_id)
            if state.status in ("completed", "error"):
                state.elapsed_seconds = round(time.monotonic() - start_time, 2)
                return state
            await asyncio.sleep(1.0)

    async def get_state(self, prompt_id: str) -> ProgressState:
        """Get current state via HTTP fallback (queue + history)."""
        state = ProgressState(prompt_id=prompt_id)

        # Check history first (completed jobs)
        with contextlib.suppress(httpx.HTTPError, OSError):
            history = await self._client.get_history_item(prompt_id)
            if prompt_id in history:
                state.status = "completed"
                entry = history[prompt_id]
                outputs = entry.get("outputs", {})
                for _node_id, node_output in outputs.items():
                    for key in ("images", "gifs"):
                        for item in node_output.get(key, []):
                            state.outputs.append(
                                {
                                    "node_id": _node_id,
                                    "filename": item.get("filename", ""),
                                    "subfolder": item.get("subfolder", ""),
                                }
                            )
                return state

        # Check queue (running/pending)
        with contextlib.suppress(httpx.HTTPError, OSError):
            queue = await self._client.get_queue()
            for item in queue.get("queue_running", []):
                if len(item) >= 2 and item[1] == prompt_id:
                    state.status = "running"
                    return state
            pending = queue.get("queue_pending", [])
            for i, item in enumerate(pending):
                if len(item) >= 2 and item[1] == prompt_id:
                    state.status = "queued"
                    state.queue_position = i + 1
                    return state

        return state
