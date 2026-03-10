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


def _apply_remove_node(workflow: dict[str, Any], op: dict[str, Any]) -> None:
    """Remove a node and clean up dangling references."""
    node_id = op.get("node_id")
    if not node_id:
        raise ValueError("remove_node requires 'node_id'")
    if node_id not in workflow:
        raise ValueError(f"Node '{node_id}' not found")
    del workflow[node_id]
    for node_data in workflow.values():
        inputs = node_data.get("inputs", {})
        to_remove = []
        for key, value in inputs.items():
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and value[0] == node_id
            ):
                to_remove.append(key)
        for key in to_remove:
            del inputs[key]


def _apply_set_input(workflow: dict[str, Any], op: dict[str, Any]) -> None:
    """Set an input value on a node."""
    node_id = op.get("node_id")
    if not node_id:
        raise ValueError("set_input requires 'node_id'")
    if node_id not in workflow:
        raise ValueError(f"Node '{node_id}' not found")
    input_name = op.get("input_name")
    if not input_name:
        raise ValueError("set_input requires 'input_name'")
    if "value" not in op:
        raise ValueError("set_input requires 'value'")
    workflow[node_id]["inputs"][input_name] = op["value"]


def _apply_connect(workflow: dict[str, Any], op: dict[str, Any]) -> None:
    """Connect one node's output to another node's input."""
    from_node = op.get("from_node")
    if not from_node:
        raise ValueError("connect requires 'from_node'")
    to_node = op.get("to_node")
    if not to_node:
        raise ValueError("connect requires 'to_node'")
    if from_node not in workflow:
        raise ValueError(f"Source node '{from_node}' not found")
    if to_node not in workflow:
        raise ValueError(f"Target node '{to_node}' not found")
    from_output = op.get("from_output", 0)
    if not isinstance(from_output, int) or from_output < 0:
        raise ValueError("connect requires 'from_output' to be a non-negative integer")
    to_input = op.get("to_input")
    if not to_input:
        raise ValueError("connect requires non-empty 'to_input'")
    workflow[to_node]["inputs"][to_input] = [from_node, from_output]


def _apply_disconnect(workflow: dict[str, Any], op: dict[str, Any]) -> None:
    """Clear a connection on a node's input."""
    node_id = op.get("node_id")
    if not node_id:
        raise ValueError("disconnect requires 'node_id'")
    if node_id not in workflow:
        raise ValueError(f"Node '{node_id}' not found")
    input_name = op.get("input_name")
    if not input_name:
        raise ValueError("disconnect requires 'input_name'")
    inputs = workflow[node_id]["inputs"]
    if input_name not in inputs:
        raise ValueError(f"Node '{node_id}' has no input '{input_name}'")
    del inputs[input_name]


def apply_operations(workflow: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a list of operations to a workflow. Returns a new workflow dict.

    Operations execute sequentially. If any fails, the original workflow
    is unchanged (atomic — operates on a deep copy).
    """
    result = copy.deepcopy(workflow)
    dispatch: dict[str, Any] = {
        "add_node": _apply_add_node,
        "remove_node": _apply_remove_node,
        "set_input": _apply_set_input,
        "connect": _apply_connect,
        "disconnect": _apply_disconnect,
    }
    for i, op in enumerate(operations):
        op_type = op.get("op")
        handler = dispatch.get(op_type) if op_type else None
        if handler is None:
            raise ValueError(f"Operation {i}: unknown op '{op_type}'")
        handler(result, op)
    return result
