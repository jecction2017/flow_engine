"""In-memory Kafka transport for tests and local development."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from flow_engine.connectors.backends.kafka.messages import BusMessage, Position
from flow_engine.connectors.config_kafka import (
    ConsumeStrategySpec,
    KafkaConsumerSpec,
    ResolvedConsumerRef,
    ResolvedProducerRef,
)


@dataclass
class _FakeTopicState:
    messages: list[BusMessage] = field(default_factory=list)
    next_offset: int = 0


class MemoryKafkaTransport:
    """Process-global in-memory topics (like prior FakeMessageBusBackend)."""

    _topics: dict[str, _FakeTopicState] = {}
    _lock = asyncio.Lock()

    @classmethod
    def reset_all(cls) -> None:
        cls._topics.clear()

    @classmethod
    async def publish(
        cls,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        partition: int = 0,
    ) -> BusMessage:
        async with cls._lock:
            st = cls._topics.setdefault(topic, _FakeTopicState())
            offset = st.next_offset
            st.next_offset += 1
            msg = BusMessage(
                topic=topic,
                partition=partition,
                offset=offset,
                key=key,
                value=value,
                timestamp_ms=int(time.time() * 1000),
            )
            st.messages.append(msg)
            return msg

    @classmethod
    async def poll(
        cls,
        consumer_ref: ResolvedConsumerRef,
        *,
        max_records: int,
        timeout_ms: int,
        committed: dict[tuple[str, int], int],
        paused: bool,
        partitions_override: list[int] | None,
    ) -> list[BusMessage]:
        if paused:
            await asyncio.sleep(min(timeout_ms, 100) / 1000.0)
            return []
        topic = consumer_ref.topic
        deadline = time.monotonic() + timeout_ms / 1000.0
        part_filter = partitions_override if partitions_override is not None else consumer_ref.spec.partitions
        out: list[BusMessage] = []
        while len(out) < max_records:
            async with cls._lock:
                st = cls._topics.get(topic)
                batch: list[BusMessage] = []
                if st is not None:
                    for msg in st.messages:
                        key = (msg.topic, msg.partition)
                        last = committed.get(key, -1)
                        if msg.offset > last:
                            if part_filter is None or msg.partition in part_filter:
                                batch.append(msg)
                batch.sort(key=lambda m: (m.partition, m.offset))
                for msg in batch:
                    if len(out) >= max_records:
                        break
                    key = (msg.topic, msg.partition)
                    if msg.offset > committed.get(key, -1):
                        out.append(msg)
            if out:
                return out
            if time.monotonic() >= deadline:
                return []
            await asyncio.sleep(0.05)

    @classmethod
    async def commit(cls, committed: dict[tuple[str, int], int], positions: list[Position]) -> None:
        for pos in positions:
            committed[(pos.topic, pos.partition)] = pos.offset


class MemoryConsumerSession:
    def __init__(
        self,
        consumer_ref: ResolvedConsumerRef,
        *,
        partitions_override: list[int] | None,
        strategy_override: ConsumeStrategySpec | str | dict[str, Any] | None,
    ) -> None:
        self._ref = consumer_ref
        self._partitions_override = partitions_override
        self._committed: dict[tuple[str, int], int] = {}
        self._paused = False
        _ = strategy_override

    async def poll(self, *, max_records: int, timeout_ms: int) -> list[BusMessage]:
        return await MemoryKafkaTransport.poll(
            self._ref,
            max_records=max_records,
            timeout_ms=timeout_ms,
            committed=self._committed,
            paused=self._paused,
            partitions_override=self._partitions_override,
        )

    async def commit(self, positions: list[Position]) -> None:
        await MemoryKafkaTransport.commit(self._committed, positions)

    async def pause(self) -> None:
        self._paused = True

    async def resume(self) -> None:
        self._paused = False

    async def close(self) -> None:
        pass


async def memory_receive_bounded(
    consumer_ref: ResolvedConsumerRef,
    *,
    max_records: int,
    timeout_ms: int,
    partitions: list[int] | None,
    strategy: Any,
) -> list[BusMessage]:
    _ = strategy
    committed: dict[tuple[str, int], int] = {}
    return await MemoryKafkaTransport.poll(
        consumer_ref,
        max_records=max_records,
        timeout_ms=timeout_ms,
        committed=committed,
        paused=False,
        partitions_override=partitions,
    )


async def memory_send(
    producer_ref: ResolvedProducerRef,
    *,
    value: bytes,
    key: bytes | None,
    partition: int | None,
) -> dict[str, Any]:
    part = partition if partition is not None else 0
    msg = await MemoryKafkaTransport.publish(
        producer_ref.topic, value, key=key, partition=part
    )
    return {"topic": msg.topic, "partition": msg.partition, "offset": msg.offset}
