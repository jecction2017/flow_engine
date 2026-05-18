"""Per-instance concurrency gate."""

from __future__ import annotations

import threading


class ConcurrencyGate:
    def __init__(self, max_in_flight: int) -> None:
        self._sem = threading.BoundedSemaphore(max(1, max_in_flight))

    def acquire(self) -> None:
        if not self._sem.acquire(blocking=False):
            raise RuntimeError("CONNECTOR_CONCURRENCY_LIMIT")

    def release(self) -> None:
        self._sem.release()
