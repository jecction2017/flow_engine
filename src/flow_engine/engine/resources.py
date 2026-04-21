"""Process/thread pools, global concurrency gate, and signal hooks."""

from __future__ import annotations

import asyncio
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
_cancel_lock = threading.Lock()
_signal_handlers_installed = False
_previous_signal_handlers: dict[int, Any] = {}


def register_cancel(fn: Callable[[], Any]) -> Callable[[], None]:
    """Register a cancellation hook. Returns a deregister callable to avoid leaks
    across repeated runs of the same process (e.g. test suites)."""
    with _cancel_lock:
        _cancel_registry.append(fn)

    def _deregister() -> None:
        with _cancel_lock:
            try:
                _cancel_registry.remove(fn)
            except ValueError:
                pass

    return _deregister


def _snapshot_cancel_hooks() -> list[Callable[[], Any]]:
    with _cancel_lock:
        return list(_cancel_registry)


def _on_signal(signum: int, frame: Any) -> None:
    logger.warning("Signal %s received; propagating cancellation.", signum)
    for fn in _snapshot_cancel_hooks():
        try:
            fn()
        except Exception:  # noqa: BLE001
            logger.exception("Cancel hook failed")
    prev = _previous_signal_handlers.get(signum)
    if prev is None or prev is _on_signal:
        return
    try:
        if callable(prev):
            prev(signum, frame)
    except KeyboardInterrupt:
        # Keep the normal SIGINT semantics for callers (e.g. uvicorn CLI).
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Previous signal handler failed")


def install_signal_handlers() -> None:
    """Idempotent: register signal + atexit hooks only once per process."""
    global _signal_handlers_installed
    if _signal_handlers_installed:
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            _previous_signal_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, _on_signal)
        except (AttributeError, ValueError):
            # Windows may not support SIGTERM on all contexts; the main-thread
            # requirement of signal.signal also fails inside non-main threads.
            pass

    def _atexit() -> None:
        for fn in _snapshot_cancel_hooks():
            try:
                fn()
            except Exception:  # noqa: BLE001
                pass

    atexit.register(_atexit)
    _signal_handlers_installed = True


def asyncio_main_cancel(loop: asyncio.AbstractEventLoop) -> Callable[[], None]:
    """Register a hook that cancels all asyncio tasks for `loop` (best-effort).

    Returns a deregister callable so callers can tear the hook down when their
    runtime ends, preventing unbounded accumulation over many `run()` calls.
    """

    def _cancel() -> None:
        try:
            if loop.is_closed():
                return
            for t in asyncio.all_tasks(loop):
                t.cancel()
        except RuntimeError:
            pass

    return register_cancel(_cancel)
