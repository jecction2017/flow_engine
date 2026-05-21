"""Kafka I/O operations used by KafkaClusterHandle."""

from __future__ import annotations

import logging
from typing import Any

from flow_engine.connectors.backends.kafka import client_factory as cf
from flow_engine.connectors.backends.kafka import fake_transport, strategy
from flow_engine.connectors.backends.kafka.messages import BusMessage, Position, message_to_dict
from flow_engine.connectors.config_kafka import (
    ConsumeStrategySpec,
    KafkaDefaults,
    ResolvedConsumerRef,
    ResolvedProducerRef,
)

logger = logging.getLogger(__name__)


def _headers_to_dict(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in headers or []:
        if not item:
            continue
        k, v = item[0], item[1] if len(item) > 1 else b""
        key = k.decode() if isinstance(k, bytes) else str(k)
        val = v.decode() if isinstance(v, bytes) else str(v)
        out[key] = val
    return out


def _record_to_bus_message(rec: Any) -> BusMessage:
    return BusMessage(
        topic=rec.topic,
        partition=rec.partition,
        offset=rec.offset,
        key=rec.key,
        value=rec.value or b"",
        headers=_headers_to_dict(rec.headers),
        timestamp_ms=rec.timestamp,
    )


async def receive_bounded(
    consumer_ref: ResolvedConsumerRef,
    defaults: KafkaDefaults,
    *,
    max_records: int,
    timeout_ms: int,
    partitions: list[int] | None,
    strategy_override: Any,
) -> list[dict[str, Any]]:
    import uuid
    from dataclasses import replace

    strat = strategy.resolve_strategy(consumer_ref.spec.strategy, strategy_override)
    # Ephemeral group so kafka_receive does not rebalance against a long-lived
    # subscription session using the same dictionary group_id.
    bounded_ref = consumer_ref
    if consumer_ref.cluster.transport != "memory":
        ephemeral_group = f"{consumer_ref.spec.group_id}-bounded-{uuid.uuid4().hex[:12]}"
        bounded_ref = replace(
            consumer_ref,
            spec=consumer_ref.spec.model_copy(update={"group_id": ephemeral_group}),
        )
    if bounded_ref.cluster.transport == "memory":
        raw = await fake_transport.memory_receive_bounded(
            bounded_ref,
            max_records=max_records,
            timeout_ms=timeout_ms,
            partitions=partitions,
            strategy=strat,
        )
    else:
        consumer = await cf.create_consumer(
            bounded_ref,
            defaults,
            partitions_override=partitions,
            strategy=strat,
        )
        try:
            await strategy.apply_consume_strategy(consumer, strat)
            raw_batch = await consumer.getmany(timeout_ms=timeout_ms, max_records=max_records)
            raw: list[BusMessage] = []
            for _tp, records in raw_batch.items():
                for rec in records:
                    raw.append(_record_to_bus_message(rec))
                    if len(raw) >= max_records:
                        break
                if len(raw) >= max_records:
                    break
        finally:
            await cf.stop_client(consumer)

    ser = consumer_ref.spec.serializers
    return [
        message_to_dict(
            m,
            key=cf.deserialize_key(m.key, ser),
            value=cf.deserialize_value(m.value, ser),
        )
        for m in raw
    ]


async def send_message(
    producer_ref: ResolvedProducerRef,
    defaults: KafkaDefaults,
    *,
    value: Any,
    key: Any = None,
    partition: int | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    ser = producer_ref.spec.serializers
    val_b = cf.serialize_value(value, ser)
    key_b = cf.serialize_key(key, ser)
    hdrs = [(k, v.encode("utf-8")) for k, v in (headers or {}).items()]

    if producer_ref.cluster.transport == "memory":
        result = await fake_transport.memory_send(
            producer_ref,
            value=val_b,
            key=key_b,
            partition=partition,
        )
    else:
        producer = await cf.create_producer(
            producer_ref.cluster, producer_ref.spec, defaults
        )
        try:
            meta = await producer.send_and_wait(
                producer_ref.topic,
                val_b,
                key=key_b,
                partition=partition,
                headers=hdrs or None,
            )
            result = {
                "topic": meta.topic,
                "partition": meta.partition,
                "offset": meta.offset,
            }
        finally:
            await cf.stop_client(producer)

    logger.info(
        "business_kafka_send",
        extra={
            "producer_id": producer_ref.producer_id,
            "topic": producer_ref.topic,
            "partition": result.get("partition"),
            "offset": result.get("offset"),
        },
    )
    return result


class RealConsumerSession:
    def __init__(self, consumer: Any, consumer_ref: ResolvedConsumerRef) -> None:
        self._consumer = consumer
        self._ref = consumer_ref

    async def poll(self, *, max_records: int, timeout_ms: int) -> list[BusMessage]:
        raw = await self._consumer.getmany(timeout_ms=timeout_ms, max_records=max_records)
        out: list[BusMessage] = []
        for _tp, records in raw.items():
            for rec in records:
                out.append(_record_to_bus_message(rec))
                if len(out) >= max_records:
                    return out
        return out

    async def commit(self, positions: list[Position]) -> None:
        if not positions:
            return
        from aiokafka import OffsetAndMetadata, TopicPartition

        offsets = {
            TopicPartition(p.topic, p.partition): OffsetAndMetadata(p.offset + 1, "")
            for p in positions
        }
        await self._consumer.commit(offsets)

    async def pause(self) -> None:
        parts = self._consumer.assignment()
        if parts:
            self._consumer.pause(*parts)

    async def resume(self) -> None:
        paused = self._consumer.paused()
        if paused:
            self._consumer.resume(*paused)
        parts = self._consumer.assignment()
        if parts:
            self._consumer.resume(*parts)

    async def close(self) -> None:
        await cf.stop_client(self._consumer)


async def open_consumer_session(
    consumer_ref: ResolvedConsumerRef,
    defaults: KafkaDefaults,
    *,
    partitions_override: list[int] | None,
    strategy_override: Any,
) -> RealConsumerSession | fake_transport.MemoryConsumerSession:
    strat = strategy.resolve_strategy(consumer_ref.spec.strategy, strategy_override)
    if consumer_ref.cluster.transport == "memory":
        return fake_transport.MemoryConsumerSession(
            consumer_ref,
            partitions_override=partitions_override,
            strategy_override=strat,
        )
    consumer = await cf.create_consumer(
        consumer_ref,
        defaults,
        partitions_override=partitions_override,
        strategy=strat,
    )
    await strategy.apply_consume_strategy(consumer, strat)
    return RealConsumerSession(consumer, consumer_ref)
