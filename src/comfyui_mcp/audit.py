"""Structured audit logging for all MCP tool invocations."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_serializer

_logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "authorization"}


def _redact_sensitive(data: dict[str, object]) -> dict[str, object]:
    """Remove sensitive keys from a dictionary."""
    return {k: v for k, v in data.items() if k.lower() not in _SENSITIVE_KEYS}


class AuditRecord(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    tool: str
    action: str
    prompt_id: str = ""
    nodes_used: list[str] = []
    warnings: list[str] = []
    duration_ms: int = 0
    status: str = ""
    extra: dict[str, object] = {}

    @model_serializer
    def serialize(self) -> dict[str, object]:
        data: dict[str, object] = {
            "timestamp": self.timestamp,
            "tool": self.tool,
            "action": self.action,
        }
        if self.prompt_id:
            data["prompt_id"] = self.prompt_id
        if self.nodes_used:
            data["nodes_used"] = self.nodes_used
        if self.warnings:
            data["warnings"] = self.warnings
        if self.duration_ms:
            data["duration_ms"] = self.duration_ms
        if self.status:
            data["status"] = self.status
        if self.extra:
            data["extra"] = _redact_sensitive(self.extra)
        return data


class AuditLogger:
    def __init__(self, audit_file: Path) -> None:
        self._audit_file = Path(audit_file)
        self._dir_created = False
        self._lock = threading.Lock()

    def _is_path_safe(self) -> bool:
        """Check that neither the audit file nor any parent is a symlink.

        Uses is_symlink() which detects both live and dangling symlinks
        (unlike exists() which returns False for dangling symlinks).
        """
        if self._audit_file.is_symlink():
            return False
        return all(not parent.is_symlink() for parent in self._audit_file.parents)

    def _ensure_dir(self) -> bool:
        """Create parent directories once. Returns False on failure."""
        if self._dir_created:
            return True
        try:
            self._audit_file.parent.mkdir(parents=True, exist_ok=True)
            self._dir_created = True
            return True
        except OSError as e:
            _logger.error("AUDIT LOG FAILURE: cannot create directory: %s", e)
            return False

    def _write_record(self, record: AuditRecord) -> None:
        """Synchronous, thread-safe write of a single audit record."""
        with self._lock:
            # Check symlink safety on every write (not cached) to detect
            # post-init symlink swaps on the file or any parent directory
            if not self._is_path_safe():
                _logger.error(
                    "AUDIT LOG REFUSED: path contains symlink: %s",
                    self._audit_file,
                )
                return
            if not self._ensure_dir():
                return
            try:
                with open(self._audit_file, "a") as f:
                    f.write(record.model_dump_json() + "\n")
            except OSError as e:
                _logger.error("AUDIT LOG FAILURE: %s", e)

    def log(self, *, tool: str, action: str, **kwargs: Any) -> AuditRecord:
        """Write an audit record as a JSON line (synchronous)."""
        record = AuditRecord(tool=tool, action=action, **kwargs)
        self._write_record(record)
        return record

    async def async_log(self, *, tool: str, action: str, **kwargs: Any) -> AuditRecord:
        """Write an audit record without blocking the event loop."""
        record = AuditRecord(tool=tool, action=action, **kwargs)
        await asyncio.to_thread(self._write_record, record)
        return record
