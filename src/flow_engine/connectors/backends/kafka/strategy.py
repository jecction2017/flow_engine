"""Apply consume strategies after partition assignment."""

from __future__ import annotations

from typing import Any

from flow_engine.connectors.config_kafka import ConsumeStrategySpec


def resolve_strategy(
    spec_strategy: ConsumeStrategySpec | str,
    override: str | dict[str, Any] | ConsumeStrategySpec | None,
) -> ConsumeStrategySpec:
    if override is None:
        if isinstance(spec_strategy, ConsumeStrategySpec):
            return spec_strategy
        return ConsumeStrategySpec(mode=spec_strategy)  # type: ignore[arg-type]
    if isinstance(override, ConsumeStrategySpec):
        return override
    if isinstance(override, str):
        return ConsumeStrategySpec(mode=override)  # type: ignore[arg-type]
    mode = override.get("mode") or override.get("strategy") or "default"
    return ConsumeStrategySpec(
        mode=mode,  # type: ignore[arg-type]
        offsets=override.get("offsets"),
        timestamp_ms=override.get("timestamp_ms"),
    )


async def apply_consume_strategy(consumer: Any, strategy: ConsumeStrategySpec) -> None:
    if strategy.mode == "default":
        return
    from aiokafka import TopicPartition

    assigned = consumer.assignment()
    if not assigned:
        return
    if strategy.mode == "earliest":
        await consumer.seek_to_beginning(*assigned)
    elif strategy.mode == "latest":
        await consumer.seek_to_end(*assigned)
    elif strategy.mode == "offset":
        if not strategy.offsets:
            return
        for tp in assigned:
            off = strategy.offsets.get(tp.partition)
            if off is not None:
                await consumer.seek(TopicPartition(tp.topic, tp.partition), off)
    elif strategy.mode == "timestamp":
        if strategy.timestamp_ms is None:
            return
        timestamps = {tp: strategy.timestamp_ms for tp in assigned}
        offsets = await consumer.offsets_for_times(timestamps)
        for tp, omd in offsets.items():
            if omd is not None and omd.offset >= 0:
                await consumer.seek(tp, omd.offset)
