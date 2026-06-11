from __future__ import annotations

import asyncio
import copy
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
from typing import Any, Awaitable, Callable

from flow_engine.cache.protocol import CacheBackend, CacheSetOptions


@dataclass(slots=True)
class _CacheEntry:
    value: Any
    expires_at: float | None


@dataclass(slots=True)
class _NamespaceStore:
    entries: OrderedDict[str, _CacheEntry]
    max_entries: int


class MemoryLruCacheBackend(CacheBackend):
    def __init__(self, *, default_max_entries: int = 1024) -> None:
        self._default_max_entries = max(1, int(default_max_entries))
        self._stores: dict[str, _NamespaceStore] = {}
        self._inflight: dict[tuple[str, str], asyncio.Future[Any]] = {}
        self._lock = RLock()

    def get(self, namespace: str, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            store = self._stores.get(namespace)
            if store is None:
                return None
            entry = store.entries.get(key)
            if entry is None:
                return None
            if entry.expires_at is not None and entry.expires_at <= now:
                del store.entries[key]
                return None
            store.entries.move_to_end(key)
            return copy.deepcopy(entry.value)

    def set(self, namespace: str, key: str, value: Any, *, options: CacheSetOptions | None = None) -> None:
        opts = options or CacheSetOptions()
        ttl_seconds = opts.ttl_seconds
        max_entries = opts.max_entries
        expires_at = None
        if ttl_seconds is not None:
            ttl_num = float(ttl_seconds)
            if ttl_num <= 0:
                return
            expires_at = time.monotonic() + ttl_num
        with self._lock:
            store = self._stores.get(namespace)
            if store is None:
                store = _NamespaceStore(
                    entries=OrderedDict(),
                    max_entries=self._default_max_entries,
                )
                self._stores[namespace] = store
            if max_entries is not None:
                store.max_entries = max(1, int(max_entries))
            store.entries[key] = _CacheEntry(value=copy.deepcopy(value), expires_at=expires_at)
            store.entries.move_to_end(key)
            while len(store.entries) > store.max_entries:
                store.entries.popitem(last=False)

    def delete(self, namespace: str, key: str) -> bool:
        with self._lock:
            store = self._stores.get(namespace)
            if store is None:
                return False
            return store.entries.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._stores.clear()
            self._inflight.clear()

    async def get_or_compute(
        self,
        namespace: str,
        key: str,
        compute: Callable[[], Awaitable[Any]],
        *,
        options: CacheSetOptions | None = None,
    ) -> tuple[Any, bool]:
        cached = self.get(namespace, key)
        if cached is not None:
            return cached, True

        token = (namespace, key)
        with self._lock:
            existing = self._inflight.get(token)
            if existing is None:
                loop = asyncio.get_running_loop()
                existing = loop.create_future()
                self._inflight[token] = existing
                owner = True
            else:
                owner = False

        if not owner:
            return await asyncio.shield(existing), True

        try:
            value = await compute()
        except BaseException as exc:  # noqa: BLE001
            if not existing.done():
                existing.set_exception(exc)
                # Mark as retrieved so owner-only failures do not trigger
                # "Future exception was never retrieved" warnings.
                _ = existing.exception()
            raise
        else:
            if options is not None:
                self.set(namespace, key, value, options=options)
            if not existing.done():
                existing.set_result(copy.deepcopy(value))
            return value, False
        finally:
            with self._lock:
                self._inflight.pop(token, None)
