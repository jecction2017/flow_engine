"""Namespace context bus and stack-based path resolution."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from flow_engine.engine.exceptions import FlowEngineError


class PathResolutionError(FlowEngineError):
    """Invalid or unknown path."""


def _parse_segments(path: str) -> list[str]:
    p = path.strip()
    if not p.startswith("$."):
        raise PathResolutionError(f"Path must start with '$.': {path!r}")
    rest = p[2:]
    if not rest:
        return []
    return rest.split(".")


@dataclass
class ContextFrame:
    """One stack frame: local namespace, optional loop item, and identifiers for lookup."""

    node_id: str
    alias: str | None = None
    local: dict[str, Any] = field(default_factory=dict)
    loop_item: Any | None = None
    loop_alias: str | None = None


class ContextStack:
    """Fork-on-branch: clone stacks for concurrent branches; locals stay isolated."""

    def __init__(self, global_ns: dict[str, Any] | None = None) -> None:
        self.global_ns: dict[str, Any] = global_ns if global_ns is not None else {}
        self._frames: list[ContextFrame] = []

    def fork(self) -> ContextStack:
        """Deep copy global reference (same dict) and copy frames for branch isolation."""
        c = ContextStack(self.global_ns)
        c._frames = [ContextFrame(f.node_id, f.alias, copy.copy(f.local), f.loop_item, f.loop_alias) for f in self._frames]
        return c

    def push(self, frame: ContextFrame) -> None:
        self._frames.append(frame)

    def pop(self) -> ContextFrame:
        return self._frames.pop()

    @property
    def frames(self) -> list[ContextFrame]:
        return self._frames

    def find_frame_by_ident(self, ident: str) -> ContextFrame | None:
        for f in reversed(self._frames):
            if ident == f.node_id or (f.alias and ident == f.alias):
                return f
        return None

    def get_path(self, path: str) -> Any:
        segments = _parse_segments(path)
        if not segments:
            raise PathResolutionError("Empty path after '$.'")
        head, *tail = segments
        if head == "global":
            return self._dig(self.global_ns, tail)
        if head == "local":
            if not self._frames:
                raise PathResolutionError("No frame for $.local")
            return self._dig(self._frames[-1].local, tail)
        if head == "item":
            for f in reversed(self._frames):
                if f.loop_item is not None:
                    if not tail:
                        return f.loop_item
                    return self._dig_any(f.loop_item, tail)
            raise PathResolutionError("$.item used outside of a loop with current item")
        fr = self.find_frame_by_ident(head)
        if fr is None:
            raise PathResolutionError(f"Unknown namespace or id: {head!r}")
        if not tail:
            return fr.local
        return self._dig(fr.local, tail)

    def set_path(self, path: str, value: Any) -> None:
        segments = _parse_segments(path)
        if not segments:
            raise PathResolutionError("Empty path after '$.'")
        head, *tail = segments
        if head == "global":
            self._set_container(self.global_ns, tail, value)
            return
        if head == "local":
            if not self._frames:
                raise PathResolutionError("No frame for $.local")
            self._set_container(self._frames[-1].local, tail, value)
            return
        if head == "item":
            for f in reversed(self._frames):
                if f.loop_item is not None:
                    self._set_any(f.loop_item, tail, value)
                    return
            raise PathResolutionError("$.item not active")
        fr = self.find_frame_by_ident(head)
        if fr is None:
            raise PathResolutionError(f"Unknown namespace or id: {head!r}")
        self._set_container(fr.local, tail, value)

    @staticmethod
    def _dig(obj: dict[str, Any], tail: list[str]) -> Any:
        cur: Any = obj
        for part in tail:
            if not isinstance(cur, dict):
                raise PathResolutionError(f"Cannot traverse non-dict at {part!r}")
            cur = cur[part]
        return cur

    @staticmethod
    def _dig_any(obj: Any, tail: list[str]) -> Any:
        cur = obj
        for part in tail:
            if isinstance(cur, dict):
                cur = cur[part]
            else:
                cur = getattr(cur, part)
        return cur

    @staticmethod
    def _set_container(root: dict[str, Any], tail: list[str], value: Any) -> None:
        if not tail:
            raise PathResolutionError("Cannot assign to container root without key")
        cur = root
        for part in tail[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[tail[-1]] = value

    @staticmethod
    def _set_any(obj: Any, tail: list[str], value: Any) -> None:
        if not tail:
            raise PathResolutionError("Invalid assignment target on $.item")
        cur = obj
        for part in tail[:-1]:
            if isinstance(cur, dict):
                nxt = cur.get(part)
                if not isinstance(nxt, dict):
                    nxt = {}
                    cur[part] = nxt
                cur = nxt
            else:
                cur = getattr(cur, part)
        last = tail[-1]
        if isinstance(cur, dict):
            cur[last] = value
        else:
            setattr(cur, last, value)
