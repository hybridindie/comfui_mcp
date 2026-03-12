"""Structured audit logging for all MCP tool invocations."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, model_serializer

_SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "authorization"}

logger = logging.getLogger(__name__)


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

    def _ensure_directory(self) -> None:
        """Create parent directories on first write, with symlink check."""
        if self._dir_created:
            return
        parent = self._audit_file.parent
        parent.mkdir(parents=True, exist_ok=True)
        # Reject symlinked audit file — could redirect entries to attacker-controlled path
        if self._audit_file.exists() and self._audit_file.is_symlink():
            raise OSError(f"Audit log path is a symlink — refusing to write: {self._audit_file}")
        self._dir_created = True

    def log(self, *, tool: str, action: str, **kwargs) -> AuditRecord:
        """Write an audit record as a JSON line.

        Raises OSError on write failure — audit log integrity is a security
        requirement, so failures must not be silently swallowed.
        """
        record = AuditRecord(tool=tool, action=action, **kwargs)
        try:
            self._ensure_directory()
            with open(self._audit_file, "a") as f:
                f.write(record.model_dump_json() + "\n")
        except OSError:
            logger.exception("AUDIT LOG FAILURE — cannot write to %s", self._audit_file)
            raise
        return record
