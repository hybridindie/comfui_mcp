"""Node danger detection - dynamically identify potentially dangerous nodes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_DANGEROUS_NAME_PATTERNS = [
    re.compile(r"\bexec\b", re.IGNORECASE),
    re.compile(r"\beval\b", re.IGNORECASE),
    re.compile(r"\bshell\b", re.IGNORECASE),
    re.compile(r"\bcmd\b", re.IGNORECASE),
    re.compile(r"\bcommand\b", re.IGNORECASE),
    re.compile(r"\bpythonexec\b", re.IGNORECASE),
    re.compile(r"\brunpython\b", re.IGNORECASE),
    re.compile(r"\bos\.system\b", re.IGNORECASE),
    re.compile(r"\bsubprocess\b", re.IGNORECASE),
    re.compile(r"\bterminal\b", re.IGNORECASE),
    re.compile(r"\bconsole\b", re.IGNORECASE),
    re.compile(r"\bscript\b.*exec\b", re.IGNORECASE),
]

_DANGEROUS_INPUT_TYPES = {
    "CODE",
    "PYTHON",
    "COMMAND",
    "COMMANDLINE",
}

_DANGEROUS_CATEGORY_PATTERNS = [
    re.compile(r"execute", re.IGNORECASE),
    re.compile(r"run.*code", re.IGNORECASE),
    re.compile(r"python.*run", re.IGNORECASE),
    re.compile(r"script.*run", re.IGNORECASE),
]


@dataclass
class DangerousNode:
    node_class: str
    reason: str
    category: str


@dataclass
class NodeAuditResult:
    total_nodes: int = 0
    dangerous_nodes: list[DangerousNode] = field(default_factory=list)
    suspicious_nodes: list[DangerousNode] = field(default_factory=list)

    @property
    def dangerous_count(self) -> int:
        return len(self.dangerous_nodes)

    @property
    def suspicious_count(self) -> int:
        return len(self.suspicious_nodes)


class NodeAuditor:
    def __init__(
        self,
        dangerous_patterns: list[re.Pattern] | None = None,
        dangerous_input_types: set[str] | None = None,
    ) -> None:
        self._dangerous_patterns = dangerous_patterns or _DANGEROUS_NAME_PATTERNS
        self._dangerous_input_types = dangerous_input_types or _DANGEROUS_INPUT_TYPES

    def audit_node_class(
        self, node_class: str, node_info: dict
    ) -> DangerousNode | None:
        reasons = []
        category = "suspicious"

        for pattern in self._dangerous_patterns:
            if pattern.search(node_class):
                reasons.append(f"Name matches pattern: {pattern.pattern}")
                category = "dangerous"
                break

        if "input" in node_info:
            for input_name, input_spec in node_info["input"].items():
                if isinstance(input_spec, dict):
                    input_type = input_spec.get("type", "")
                    if isinstance(input_type, str):
                        input_type_upper = input_type.upper()
                        if input_type_upper in self._dangerous_input_types:
                            reasons.append(f"Has dangerous input type: {input_type}")
                            category = "dangerous"

                    options = input_spec.get("options", {})
                    if isinstance(options, dict):
                        for opt_key, opt_val in options.items():
                            if isinstance(opt_val, str):
                                for pattern in self._dangerous_patterns:
                                    if pattern.search(opt_val):
                                        reasons.append(
                                            f"Option '{input_name}' contains: {pattern.pattern}"
                                        )
                                        category = "dangerous"

        if "description" in node_info:
            desc = node_info.get("description", "")
            if isinstance(desc, str):
                for pattern in _DANGEROUS_CATEGORY_PATTERNS:
                    if pattern.search(desc):
                        reasons.append(f"Description matches: {pattern.pattern}")
                        if category != "dangerous":
                            category = "suspicious"

        if reasons:
            return DangerousNode(
                node_class=node_class,
                reason="; ".join(reasons),
                category=category,
            )
        return None

    def audit_all_nodes(self, object_info: dict) -> NodeAuditResult:
        result = NodeAuditResult(total_nodes=len(object_info))

        for node_class, node_info in object_info.items():
            if not isinstance(node_info, dict):
                continue

            finding = self.audit_node_class(node_class, node_info)
            if finding:
                if finding.category == "dangerous":
                    result.dangerous_nodes.append(finding)
                else:
                    result.suspicious_nodes.append(finding)

        return result
