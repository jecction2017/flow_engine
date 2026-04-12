"""Compilation-time validation: ids, strategy refs, jump scope barriers."""

from __future__ import annotations

from typing import Iterable

from flow_engine.exceptions import CompilationError
from flow_engine.models import (
    FlowDefinition,
    FlowMember,
    LoopNode,
    OnErrorAction,
    SubflowNode,
    TaskNode,
    collect_all_node_ids,
)


def _walk(members: Iterable[FlowMember]) -> list[FlowMember]:
    out: list[FlowMember] = []
    for m in members:
        out.append(m)
        if isinstance(m, (LoopNode, SubflowNode)):
            out.extend(_walk(m.children))
    return out


def _build_parent_map(flow: FlowDefinition) -> dict[str, str | None]:
    parent: dict[str, str | None] = {}

    def rec(members: list[FlowMember], p: str | None) -> None:
        for m in members:
            nid = m.id or m.name
            parent[nid] = p
            if isinstance(m, (LoopNode, SubflowNode)):
                rec(m.children, nid)

    rec(flow.nodes, None)
    return parent


def _scope_list_for(flow: FlowDefinition, node_id: str) -> list[str]:
    """Returns ids in the same member list as node_id (including node_id)."""

    def find_list(members: list[FlowMember]) -> list[str] | None:
        ids = [x.id or x.name for x in members]
        if node_id in ids:
            return ids
        for m in members:
            if isinstance(m, (LoopNode, SubflowNode)):
                got = find_list(m.children)
                if got is not None:
                    return got
        return None

    lst = find_list(flow.nodes)
    if lst is None:
        raise CompilationError(f"Node not found: {node_id}")
    return lst


def _is_ancestor(ancestor: str, node: str, parent: dict[str, str | None]) -> bool:
    cur = parent.get(node)
    while cur is not None:
        if cur == ancestor:
            return True
        cur = parent.get(cur)
    return False


def _jump_allowed(flow: FlowDefinition, src: str, target: str, parent: dict[str, str | None]) -> bool:
    if src == target:
        return False
    if target not in collect_all_node_ids(flow.nodes):
        return False
    sibs = set(_scope_list_for(flow, src))
    if target in sibs and target != src:
        return True
    if _is_ancestor(target, src, parent):
        return True
    return False


def compile_flow(flow: FlowDefinition) -> FlowDefinition:
    """Raises CompilationError on invalid definitions."""
    all_ids = collect_all_node_ids(flow.nodes)
    if len(all_ids) != len(set(all_ids)):
        dup = [x for x in all_ids if all_ids.count(x) > 1]
        raise CompilationError(f"Duplicate node ids/names: {sorted(set(dup))}")

    for m in _walk(flow.nodes):
        if m.strategy_ref not in flow.strategies:
            raise CompilationError(f"Missing strategy {m.strategy_ref!r} for node {m.id or m.name!r}")

    parent = _build_parent_map(flow)

    for m in _walk(flow.nodes):
        if not m.on_error:
            continue
        oe = m.on_error
        act = oe.action
        if isinstance(act, str):
            act = OnErrorAction(act)
        if act == OnErrorAction.JUMP and oe.target:
            src = m.id or m.name
            if not _jump_allowed(flow, src, oe.target, parent):
                raise CompilationError(
                    f"Jump from {src!r} to {oe.target!r} violates scope barrier "
                    "(only upward or same-list targets are allowed)."
                )

    _validate_global_paths(flow)
    return flow


def _validate_global_paths(flow: FlowDefinition) -> None:
    """Ensure mapped paths use the $. prefix convention."""
    for m in _walk(flow.nodes):
        if not isinstance(m, TaskNode):
            continue
        for p in list(m.boundary.outputs.values()) + list(m.boundary.inputs.keys()):
            if not p.startswith("$."):
                raise CompilationError(f"Boundary path must start with '$.': {p!r}")
