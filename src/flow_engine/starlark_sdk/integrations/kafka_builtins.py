"""Starlark builtins for Kafka consume/produce."""

from __future__ import annotations

from typing import Any

from flow_engine.starlark_sdk.builtin_registry import BuiltinArgSpec, PythonBuiltinSpec, register_builtin
from flow_engine.starlark_sdk.integrations._kafka_helpers import cap_kafka_timeout_ms, run_kafka_operation

_KAFKA_SUPPRESSED: dict[str, Any] = {
    "ok": False,
    "error": {"code": "SUPPRESSED", "message": "integration suppressed"},
    "_suppressed": True,
}


@register_builtin(
    PythonBuiltinSpec(
        id="python://kafka/receive",
        starlark_name="kafka_receive",
        category="integration",
        summary="Kafka 有界消费（按数据字典 consumer_id）",
        signature=(
            BuiltinArgSpec(name="consumer_id", type="str"),
            BuiltinArgSpec(name="max_records", type="int", required=False),
            BuiltinArgSpec(name="timeout_ms", type="int", required=False),
            BuiltinArgSpec(name="partitions", type="list", required=False),
            BuiltinArgSpec(name="strategy", type="any", required=False),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_KAFKA_SUPPRESSED,
    )
)
def kafka_receive(
    consumer_id: str,
    max_records: int | None = None,
    timeout_ms: int | None = None,
    partitions: list[Any] | None = None,
    strategy: Any = None,
) -> dict[str, Any]:
    part_list: list[int] | None = None
    if partitions is not None:
        part_list = [int(p) for p in partitions]
    poll_ms = cap_kafka_timeout_ms(timeout_ms or 1000)
    return run_kafka_operation(
        consumer_id,
        None,
        "receive",
        max_records=max_records or 10,
        timeout_ms=poll_ms,
        partitions=part_list,
        strategy=strategy,
    )


@register_builtin(
    PythonBuiltinSpec(
        id="python://kafka/send",
        starlark_name="kafka_send",
        category="integration",
        summary="Kafka 生产（按数据字典 producer_id）",
        signature=(
            BuiltinArgSpec(name="producer_id", type="str"),
            BuiltinArgSpec(name="value", type="any"),
            BuiltinArgSpec(name="key", type="any", required=False),
            BuiltinArgSpec(name="partition", type="int", required=False),
            BuiltinArgSpec(name="headers", type="dict", required=False),
        ),
        returns="dict",
        side_effects="network",
        suppress_result=_KAFKA_SUPPRESSED,
    )
)
def kafka_send(
    producer_id: str,
    value: Any,
    key: Any = None,
    partition: int | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hdrs = {str(k): str(v) for k, v in (headers or {}).items()}
    return run_kafka_operation(
        None,
        producer_id,
        "send",
        value=value,
        key=key,
        partition=partition,
        headers=hdrs or None,
    )
