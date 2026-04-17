"""Hierarchical task tracker bridging Async, Thread, and Process futures."""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


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
        """Drain pending futures until empty, aggregating errors.

        Repeats across snapshots so that tasks spawned during callbacks (e.g.
        post-exec hooks scheduling follow-up work) are still awaited. On multi
        failure, the first is raised while remaining exceptions are logged to
        avoid silent loss.
        """
        first_exc: BaseException | None = None
        while self._pending:
            futs = list(self._pending)
            results = await asyncio.gather(*futs, return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException):
                    if first_exc is None:
                        first_exc = r
                    else:
                        logger.error("Additional tracker exception swallowed: %r", r)
        if first_exc is not None:
            raise first_exc

    @property
    def pending_count(self) -> int:
        return len(self._pending)
