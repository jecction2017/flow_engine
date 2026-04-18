"""Namespace context bus and stack-based path resolution."""

from __future__ import annotations

import copy
import threading
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
    """Fork-on-branch: clone stacks for concurrent branches; locals stay isolated.

    Thread safety
    -------------
    All public mutation / lookup methods are guarded by an internal reentrant
    lock so that concurrent workers (thread-pool tasks, ``asyncio.to_thread``
    callers, etc.) can safely read and write path values in parallel with
    the main event loop performing ``push``/``pop``/``set_path``. The lock is
    reentrant so that user-facing helpers composed of multiple primitives do
    not deadlock when they themselves are already holding it.
    """

    def __init__(
        self,
        global_ns: dict[str, Any] | None = None,
        *,
        _lock: threading.RLock | None = None,
    ) -> None:
        self.global_ns: dict[str, Any] = global_ns if global_ns is not None else {}
        self._frames: list[ContextFrame] = []
        # The optional ``_lock`` argument is used by :meth:`fork` to make the
        # child share the parent's RLock when they also share ``global_ns``;
        # otherwise concurrent writes to the same dict through two different
        # locks would race.
        self._lock = _lock or threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Expose the internal lock for call sites that need to perform a
        compound read-modify-write sequence atomically."""
        return self._lock

    def fork(self, *, clone_global: bool = False) -> ContextStack:
        """Fork the context stack for a concurrent / isolated branch.

        * ``clone_global=False`` (default): the fork shares ``global_ns`` and
          the parent's RLock so that concurrent writes from both stacks stay
          serialized against the same dict.
        * ``clone_global=True``: ``global_ns`` is deep-copied, and the fork
          receives its own lock. Writes inside the fork are fully invisible
          to the parent until an explicit merge step.

        In both cases frames are shallow-cloned so the branch can push/pop
        independently without disturbing the parent's frame stack.
        """
        with self._lock:
            if clone_global:
                c = ContextStack(copy.deepcopy(self.global_ns))
            else:
                c = ContextStack(self.global_ns, _lock=self._lock)
            c._frames = [
                ContextFrame(f.node_id, f.alias, copy.copy(f.local), f.loop_item, f.loop_alias)
                for f in self._frames
            ]
            return c

    def push(self, frame: ContextFrame) -> None:
        with self._lock:
            self._frames.append(frame)

    def pop(self) -> ContextFrame:
        with self._lock:
            return self._frames.pop()

    @property
    def frames(self) -> list[ContextFrame]:
        # Return a snapshot to avoid callers mutating the list unlocked.
        with self._lock:
            return list(self._frames)

    def find_frame_by_ident(self, ident: str) -> ContextFrame | None:
        with self._lock:
            for f in reversed(self._frames):
                if ident == f.node_id or (f.alias and ident == f.alias):
                    return f
            return None

    def get_path(self, path: str) -> Any:
        segments = _parse_segments(path)
        if not segments:
            raise PathResolutionError("Empty path after '$.'")
        head, *tail = segments
        with self._lock:
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
            fr = self._find_frame_by_ident_locked(head)
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
        with self._lock:
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
            fr = self._find_frame_by_ident_locked(head)
            if fr is None:
                raise PathResolutionError(f"Unknown namespace or id: {head!r}")
            self._set_container(fr.local, tail, value)

    def _find_frame_by_ident_locked(self, ident: str) -> ContextFrame | None:
        # Caller must hold self._lock.
        for f in reversed(self._frames):
            if ident == f.node_id or (f.alias and ident == f.alias):
                return f
        return None

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
