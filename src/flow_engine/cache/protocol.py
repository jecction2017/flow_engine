from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class CacheSetOptions:
    ttl_seconds: float | None = None
    max_entries: int | None = None


class CacheBackend(Protocol):
    def get(self, namespace: str, key: str) -> Any | None:
        ...

    def set(self, namespace: str, key: str, value: Any, *, options: CacheSetOptions | None = None) -> None:
        ...

    def delete(self, namespace: str, key: str) -> bool:
        ...

    def clear(self) -> None:
        ...
