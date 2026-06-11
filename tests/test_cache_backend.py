from __future__ import annotations

import asyncio

import pytest

from flow_engine.cache.memory import MemoryLruCacheBackend
from flow_engine.cache.protocol import CacheSetOptions


def test_memory_cache_ttl_and_lru() -> None:
    cache = MemoryLruCacheBackend(default_max_entries=2)
    cache.set("ns", "a", {"v": 1}, options=CacheSetOptions(ttl_seconds=0.01))
    assert cache.get("ns", "a") == {"v": 1}

    import time

    time.sleep(0.02)
    assert cache.get("ns", "a") is None

    cache.set("ns", "a", {"v": 1})
    cache.set("ns", "b", {"v": 2})
    cache.get("ns", "a")
    cache.set("ns", "c", {"v": 3})
    assert cache.get("ns", "b") is None
    assert cache.get("ns", "a") == {"v": 1}
    assert cache.get("ns", "c") == {"v": 3}


@pytest.mark.asyncio
async def test_memory_cache_inflight_merge() -> None:
    cache = MemoryLruCacheBackend(default_max_entries=10)
    calls = {"count": 0}

    async def compute() -> dict[str, int]:
        calls["count"] += 1
        await asyncio.sleep(0.03)
        return {"value": 42}

    async def run_one() -> tuple[dict[str, int], bool]:
        return await cache.get_or_compute("ns", "k", compute, options=None)

    results = await asyncio.gather(*(run_one() for _ in range(5)))
    assert calls["count"] == 1
    assert all(res[0] == {"value": 42} for res in results)
    assert any(hit for _, hit in results)
