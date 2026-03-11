"""Workflow inspection for detecting dangerous node types and suspicious inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_SUSPICIOUS_PATTERNS = [
    re.compile(r"__import__\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bsubprocess\b"),
    re.compile(r"\bopen\s*\(.+,\s*['\"]w"),
]


class WorkflowBlockedError(Exception):
    """Raised when a workflow is blocked in enforce mode."""


@dataclass
class InspectionResult:
    nodes_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _check_value_for_suspicious(value: Any, node_id: str, class_type: str, key: str) -> list[str]:
    """Recursively check a value for suspicious patterns."""
    warnings = []
    if isinstance(value, str):
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(value):
                warnings.append(f"Suspicious input in node {node_id} ({class_type}), field '{key}'")
                break
    elif isinstance(value, dict):
        for k, v in value.items():
            warnings.extend(_check_value_for_suspicious(v, node_id, class_type, f"{key}.{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            warnings.extend(_check_value_for_suspicious(v, node_id, class_type, f"{key}[{i}]"))
    return warnings


class WorkflowInspector:
    def __init__(
        self,
        mode: str = "audit",
        dangerous_nodes: list[str] | None = None,
        allowed_nodes: list[str] | None = None,
    ) -> None:
        self._mode = mode
        self._dangerous_nodes = set(dangerous_nodes or [])
        self._allowed_nodes = set(allowed_nodes or [])

    @property
    def mode(self) -> str:
        """Return the current inspection mode ('audit' or 'enforce')."""
        return self._mode

    def inspect(self, workflow: dict) -> InspectionResult:
        """Inspect a ComfyUI workflow and return findings."""
        nodes_used = []
        warnings = []

        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                continue
            class_type = node_data.get("class_type", "")
            if class_type:
                nodes_used.append(class_type)

            for key, value in node_data.get("inputs", {}).items():
                warnings.extend(_check_value_for_suspicious(value, node_id, class_type, key))

        # Check for dangerous nodes
        for node_type in nodes_used:
            if node_type in self._dangerous_nodes:
                warnings.append(f"Dangerous node type: {node_type}")

        # Enforce mode: block unapproved nodes
        if self._mode == "enforce" and self._allowed_nodes:
            unapproved = [n for n in nodes_used if n not in self._allowed_nodes]
            if unapproved:
                raise WorkflowBlockedError(
                    f"Workflow blocked — unapproved node types: {unapproved}"
                )

        return InspectionResult(
            nodes_used=nodes_used,
            warnings=warnings,
        )
