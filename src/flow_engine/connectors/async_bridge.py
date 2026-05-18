"""Background asyncio loop for async connector I/O from sync Starlark builtins."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop

        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_run, name="flow-engine-integration-loop", daemon=True)
        thread.start()
        _loop = loop
        _thread = thread
        return loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on the shared integration event loop (blocking)."""
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


def shutdown_integration_loop() -> None:
    """Stop background loop (tests)."""
    global _loop, _thread
    with _lock:
        if _loop is None:
            return
        loop = _loop
        _loop = None
        _thread = None
    loop.call_soon_threadsafe(loop.stop)
