"""Tests for the in-memory event bus."""

from __future__ import annotations

import asyncio

import pytest

from flow_engine.engine.event_bus import (
    InMemoryEventBus,
    get_event_bus,
    make_event,
    set_event_bus,
)


# ---------------------------------------------------------------------------
# make_event helper
# ---------------------------------------------------------------------------


def test_make_event_shape() -> None:
    ev = make_event("flow.published", "demo", {"channel": "gray"})
    assert ev["type"] == "flow.published"
    assert ev["flow_id"] == "demo"
    assert ev["data"] == {"channel": "gray"}
    assert isinstance(ev["ts"], float)


def test_make_event_default_data() -> None:
    ev = make_event("flow.stopped", "demo")
    assert ev["data"] == {}


# ---------------------------------------------------------------------------
# Singleton accessors
# ---------------------------------------------------------------------------


def test_singleton_bus_returns_same_instance() -> None:
    a = get_event_bus()
    b = get_event_bus()
    assert a is b


def test_set_event_bus_replaces_singleton() -> None:
    original = get_event_bus()
    replacement = InMemoryEventBus()
    set_event_bus(replacement)
    assert get_event_bus() is replacement
    # Restore for other tests
    set_event_bus(original)


# ---------------------------------------------------------------------------
# Publish/subscribe basics
# ---------------------------------------------------------------------------


async def test_subscriber_receives_published_events() -> None:
    bus = InMemoryEventBus()
    received: list[dict] = []

    async def listener() -> None:
        async with bus.subscribe() as events:
            async for ev in events:
                received.append(ev)
                if len(received) == 2:
                    return

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)  # ensure subscriber is registered

    await bus.publish(make_event("a", "demo"))
    await bus.publish(make_event("b", "demo"))

    await asyncio.wait_for(task, timeout=2.0)
    assert [e["type"] for e in received] == ["a", "b"]


async def test_multiple_subscribers_broadcast() -> None:
    bus = InMemoryEventBus()
    received_a: list[dict] = []
    received_b: list[dict] = []

    async def listener(out: list[dict]) -> None:
        async with bus.subscribe() as events:
            async for ev in events:
                out.append(ev)
                if len(out) == 1:
                    return

    t1 = asyncio.create_task(listener(received_a))
    t2 = asyncio.create_task(listener(received_b))
    await asyncio.sleep(0.01)
    await bus.publish(make_event("x", "demo"))
    await asyncio.gather(t1, t2)

    assert received_a[0]["type"] == "x"
    assert received_b[0]["type"] == "x"


async def test_events_published_before_subscribe_are_not_buffered() -> None:
    bus = InMemoryEventBus()
    await bus.publish(make_event("missed", "demo"))

    received: list[dict] = []

    async def listener() -> None:
        async with bus.subscribe() as events:
            async for ev in events:
                received.append(ev)
                return

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)
    await bus.publish(make_event("seen", "demo"))
    await asyncio.wait_for(task, timeout=2.0)

    assert [e["type"] for e in received] == ["seen"]


async def test_subscription_exit_unregisters_subscriber() -> None:
    bus = InMemoryEventBus()

    async def drain_one() -> None:
        async with bus.subscribe() as events:
            async for ev in events:
                return

    task = asyncio.create_task(drain_one())
    await asyncio.sleep(0.01)
    await bus.publish(make_event("one", "demo"))
    await asyncio.wait_for(task, timeout=2.0)

    # After subscriber exits, no subscribers remain
    assert bus._subscribers == []

    # Further publishes do not raise
    await bus.publish(make_event("two", "demo"))


async def test_slow_subscriber_is_evicted_when_queue_full() -> None:
    # Use a very small queue (1 slot) via direct access to confirm eviction logic.
    from flow_engine.engine.event_bus import _QueueSubscription

    bus = InMemoryEventBus()
    sub = _QueueSubscription(bus, maxsize=1)

    async def never_consume() -> None:
        async with sub:
            # Register but never iterate – queue fills up
            await asyncio.sleep(0.5)

    task = asyncio.create_task(never_consume())
    await asyncio.sleep(0.01)
    # First publish fills the queue
    await bus.publish(make_event("fill", "demo"))
    # Second publish cannot be enqueued and evicts the subscriber
    await bus.publish(make_event("overflow", "demo"))

    # After overflow eviction, the subscriber is removed
    assert len(bus._subscribers) == 0
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_publish_adds_timestamp_if_missing() -> None:
    bus = InMemoryEventBus()
    received: list[dict] = []

    async def listener() -> None:
        async with bus.subscribe() as events:
            async for ev in events:
                received.append(ev)
                return

    task = asyncio.create_task(listener())
    await asyncio.sleep(0.01)

    raw = {"type": "x", "flow_id": "demo", "data": {}}
    await bus.publish(raw)
    await asyncio.wait_for(task, timeout=2.0)

    assert "ts" in received[0]
    assert isinstance(received[0]["ts"], float)
