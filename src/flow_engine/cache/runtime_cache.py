from __future__ import annotations

import os
from threading import RLock

from flow_engine.cache.memory import MemoryLruCacheBackend
from flow_engine.cache.protocol import CacheBackend

_LOCK = RLock()
_CACHE_BACKEND: CacheBackend | None = None


def _default_cache_backend() -> CacheBackend:
    max_entries = int(os.environ.get("FLOW_ENGINE_CACHE_MAX_ENTRIES", "1024"))
    return MemoryLruCacheBackend(default_max_entries=max(1, max_entries))


def get_runtime_cache_backend() -> CacheBackend:
    global _CACHE_BACKEND
    with _LOCK:
        if _CACHE_BACKEND is None:
            _CACHE_BACKEND = _default_cache_backend()
        return _CACHE_BACKEND


def set_runtime_cache_backend(backend: CacheBackend) -> None:
    global _CACHE_BACKEND
    with _LOCK:
        _CACHE_BACKEND = backend


def reset_runtime_cache_backend() -> None:
    global _CACHE_BACKEND
    with _LOCK:
        _CACHE_BACKEND = None
