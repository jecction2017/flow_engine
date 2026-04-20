"""In-process asyncio event bus for publish/instance signalling.

Architecture
------------
* ``AbstractEventBus`` – pluggable interface (swap for Redis in multi-process setups).
* ``InMemoryEventBus`` – asyncio.Queue-based single-process implementation (default).
* ``get_event_bus()`` – module-level singleton, lazily created.

Event schema (all events are plain dicts)::

    {
        "type": "flow.published" | "flow.stopped" |
                "instance.registered" | "instance.heartbeat" | "instance.stopped" |
                "publish.state_changed",
        "flow_id": str,
        "data": dict,   # event-specific payload
        "ts": float,    # epoch seconds
    }
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class AbstractEventBus(ABC):
    @abstractmethod
    async def publish(self, event: dict[str, Any]) -> None:
        """Broadcast an event to all current subscribers."""

    @abstractmethod
    def subscribe(self) -> "Subscription":
        """Return a context manager that yields an async iterator of events."""


class Subscription(ABC):
    """Context manager returned by ``AbstractEventBus.subscribe``."""

    @abstractmethod
    async def __aenter__(self) -> AsyncIterator[dict[str, Any]]:
        ...

    @abstractmethod
    async def __aexit__(self, *_: Any) -> None:
        ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class _QueueSubscription(Subscription):
    def __init__(self, bus: "InMemoryEventBus", maxsize: int = 256) -> None:
        self._bus = bus
        self._q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    async def __aenter__(self) -> AsyncIterator[dict[str, Any]]:
        self._bus._add(self._q)
        return self._iter()

    async def __aexit__(self, *_: Any) -> None:
        self._bus._remove(self._q)

    async def _iter(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            event = await self._q.get()
            if event is _SENTINEL:
                break
            yield event


_SENTINEL: dict[str, Any] = {"type": "__sentinel__"}  # type: ignore[assignment]


class InMemoryEventBus(AbstractEventBus):
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()

    def _add(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.append(q)

    def _remove(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass
        try:
            q.put_nowait(_SENTINEL)
        except asyncio.QueueFull:
            pass

    async def publish(self, event: dict[str, Any]) -> None:
        event.setdefault("ts", time.time())
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._remove(q)

    def subscribe(self) -> _QueueSubscription:
        return _QueueSubscription(self)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def make_event(event_type: str, flow_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": event_type,
        "flow_id": flow_id,
        "data": data or {},
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_bus: AbstractEventBus | None = None


def get_event_bus() -> AbstractEventBus:
    global _bus
    if _bus is None:
        _bus = InMemoryEventBus()
    return _bus


def set_event_bus(bus: AbstractEventBus) -> None:
    """Replace the global bus (e.g. in tests or for Redis integration)."""
    global _bus
    _bus = bus
