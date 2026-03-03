"""Structured audit logging for all MCP tool invocations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, model_serializer

_SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "authorization"}


def _redact_sensitive(data: dict) -> dict:
    """Remove sensitive keys from a dictionary."""
    return {k: v for k, v in data.items() if k.lower() not in _SENSITIVE_KEYS}


class AuditRecord(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool: str
    action: str
    prompt_id: str = ""
    nodes_used: list[str] = []
    warnings: list[str] = []
    duration_ms: int = 0
    status: str = ""
    extra: dict = {}

    @model_serializer
    def serialize(self) -> dict:
        data = {
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

    def log(self, *, tool: str, action: str, **kwargs) -> AuditRecord:
        """Write an audit record as a JSON line."""
        record = AuditRecord(tool=tool, action=action, **kwargs)
        self._audit_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._audit_file, "a") as f:
            f.write(record.model_dump_json() + "\n")
        return record
