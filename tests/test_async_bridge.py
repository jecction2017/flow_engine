"""Tests for integration async bridge."""

from __future__ import annotations

import asyncio

from flow_engine.connectors.async_bridge import run_async, shutdown_integration_loop


async def _add(a: int, b: int) -> int:
    await asyncio.sleep(0.01)
    return a + b


def test_run_async_on_background_loop() -> None:
    try:
        assert run_async(_add(2, 3)) == 5
    finally:
        shutdown_integration_loop()
