"""Hierarchical task tracker bridging Async, Thread, and Process futures."""

from __future__ import annotations

import asyncio
from typing import Coroutine, TypeVar

T = TypeVar("T")


class TaskTracker:
    """Tracks pending asyncio Futures for a single branch (Fork-on-branch isolation)."""

    def __init__(self, parent: TaskTracker | None = None) -> None:
        self.parent = parent
        self._pending: set[asyncio.Future[object]] = set()

    def add(self, fut: asyncio.Future[object]) -> asyncio.Future[object]:
        self._pending.add(fut)

        def _done(f: asyncio.Future[object]) -> None:
            self._pending.discard(f)

        fut.add_done_callback(_done)
        return fut

    def create_task(self, loop: asyncio.AbstractEventLoop, coro: Coroutine[object, object, T]) -> asyncio.Task[T]:
        t = loop.create_task(coro)
        self.add(t)  # type: ignore[arg-type]
        return t

    async def wait_all(self) -> None:
        if not self._pending:
            return
        futs = list(self._pending)
        results = await asyncio.gather(*futs, return_exceptions=True)
        for r in results:
            if isinstance(r, BaseException):
                raise r

    @property
    def pending_count(self) -> int:
        return len(self._pending)
