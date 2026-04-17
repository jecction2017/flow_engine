"""Process/thread pools, global concurrency gate, and signal hooks."""

from __future__ import annotations

import atexit
import logging
import signal
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Any, Callable

from flow_engine.engine.models import ExecutionStrategy, StrategyMode

logger = logging.getLogger(__name__)


class GlobalConcurrencyGate:
    """When in-flight work hits the ceiling, callers may fall back to sync execution."""

    def __init__(self, limit: int) -> None:
        self._limit = max(1, limit)
        self._sem = threading.BoundedSemaphore(self._limit)

    def try_acquire(self) -> bool:
        return self._sem.acquire(blocking=False)

    def release(self) -> None:
        self._sem.release()


class StrategyExecutors:
    """Lazily created thread/process pools keyed by strategy name."""

    def __init__(self, strategies: dict[str, ExecutionStrategy], gate: GlobalConcurrencyGate | None = None) -> None:
        self._strategies = strategies
        self._threads: dict[str, ThreadPoolExecutor] = {}
        self._processes: dict[str, ProcessPoolExecutor] = {}
        self._gate = gate or GlobalConcurrencyGate(1024)

    def thread_pool(self, name: str) -> ThreadPoolExecutor:
        if name not in self._threads:
            st = self._strategies[name]
            self._threads[name] = ThreadPoolExecutor(max_workers=st.concurrency, thread_name_prefix=f"fe-{name}")
        return self._threads[name]

    def process_pool(self, name: str) -> ProcessPoolExecutor:
        if name not in self._processes:
            st = self._strategies[name]
            self._processes[name] = ProcessPoolExecutor(max_workers=st.concurrency)
        return self._processes[name]

    def shutdown(self) -> None:
        for ex in list(self._threads.values()):
            ex.shutdown(wait=False, cancel_futures=True)
        for ex in list(self._processes.values()):
            ex.shutdown(wait=False, cancel_futures=True)


_cancel_registry: list[Callable[[], Any]] = []


def register_cancel(fn: Callable[[], Any]) -> None:
    _cancel_registry.append(fn)


def _on_signal(signum: int, frame: Any) -> None:
    logger.warning("Signal %s received; propagating cancellation.", signum)
    for fn in _cancel_registry:
        try:
            fn()
        except Exception:  # noqa: BLE001
            logger.exception("Cancel hook failed")


def install_signal_handlers() -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (AttributeError, ValueError):
            # Windows may not support SIGTERM on all contexts
            pass

    def _atexit() -> None:
        for fn in _cancel_registry:
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    atexit.register(_atexit)


def asyncio_main_cancel(loop: asyncio.AbstractEventLoop) -> None:
    """Register a hook that cancels all asyncio tasks (best-effort)."""

    def _cancel() -> None:
        try:
            for t in asyncio.all_tasks(loop):
                t.cancel()
        except RuntimeError:
            pass

    register_cancel(_cancel)
