"""Batch operations for modifying ComfyUI workflows."""

from __future__ import annotations

import copy
from typing import Any


def _next_node_id(workflow: dict[str, Any]) -> str:
    """Generate the next integer node ID after the current max."""
    int_ids = []
    for k in workflow:
        try:
            int_ids.append(int(k))
        except ValueError:
            continue
    return str(max(int_ids, default=0) + 1)


def _apply_add_node(workflow: dict[str, Any], op: dict[str, Any]) -> None:
    """Add a node to the workflow."""
    class_type = op.get("class_type")
    if not class_type:
        raise ValueError("add_node requires 'class_type'")
    node_id = op.get("node_id") or _next_node_id(workflow)
    if node_id in workflow:
        raise ValueError(f"Node '{node_id}' already exists")
    inputs = op.get("inputs", {})
    workflow[node_id] = {"class_type": class_type, "inputs": inputs}


def apply_operations(workflow: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a list of operations to a workflow. Returns a new workflow dict.

    Operations execute sequentially. If any fails, the original workflow
    is unchanged (atomic — operates on a deep copy).
    """
    result = copy.deepcopy(workflow)
    dispatch = {
        "add_node": _apply_add_node,
    }
    for i, op in enumerate(operations):
        op_type = op.get("op")
        handler = dispatch.get(op_type) if op_type else None
        if handler is None:
            raise ValueError(f"Operation {i}: unknown op '{op_type}'")
        handler(result, op)
    return result
