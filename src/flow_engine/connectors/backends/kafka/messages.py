"""Normalized Kafka message types (shared by subscription ingress and builtins)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BusMessage:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes
    headers: dict[str, str] = field(default_factory=dict)
    timestamp_ms: int | None = None


@dataclass(frozen=True)
class Position:
    topic: str
    partition: int
    offset: int


def message_to_dict(msg: BusMessage, *, key: Any = None, value: Any = None) -> dict[str, Any]:
    return {
        "topic": msg.topic,
        "partition": msg.partition,
        "offset": msg.offset,
        "key": key if key is not None else (msg.key.decode("utf-8", "replace") if msg.key else None),
        "value": value if value is not None else msg.value.decode("utf-8", "replace"),
        "headers": dict(msg.headers),
        "timestamp_ms": msg.timestamp_ms,
    }
