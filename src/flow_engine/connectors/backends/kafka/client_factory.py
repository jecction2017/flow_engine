"""Build aiokafka clients from dictionary specs."""

from __future__ import annotations

import json
from typing import Any

from flow_engine.connectors.config import ProtectionSpec
from flow_engine.connectors.config_kafka import (
    ConsumeStrategySpec,
    KafkaAuthSpec,
    KafkaClusterSpec,
    KafkaConsumerSpec,
    KafkaDefaults,
    KafkaProducerSpec,
    ResolvedConsumerRef,
    SerializersSpec,
)
from flow_engine.connectors.protection.pipeline import ProtectionPipeline


def merged_protection(defaults: dict[str, Any], instance_raw: dict[str, Any]) -> ProtectionSpec:
    base = defaults.get("protection") or {}
    inst = instance_raw.get("protection") or {}
    merged = {**base, **inst}
    return ProtectionSpec.model_validate(merged)


def merged_consumer_params(
    defaults: KafkaDefaults,
    cluster: KafkaClusterSpec,
    consumer: KafkaConsumerSpec,
) -> dict[str, Any]:
    out = dict(defaults.consumer_params)
    out.update(consumer.params)
    out.setdefault("enable_auto_commit", False)
    return out


def merged_producer_params(
    defaults: KafkaDefaults,
    cluster: KafkaClusterSpec,
    producer: KafkaProducerSpec,
) -> dict[str, Any]:
    out = dict(defaults.producer_params)
    out.update(producer.params)
    return out


def _auth_kwargs(auth: KafkaAuthSpec) -> dict[str, Any]:
    kw: dict[str, Any] = {}
    if auth.security_protocol:
        kw["security_protocol"] = auth.security_protocol
    if auth.sasl_mechanism:
        kw["sasl_mechanism"] = auth.sasl_mechanism
    t = auth.type
    if t in ("plain", "sasl_plain", "sasl_plaintext"):
        kw["security_protocol"] = kw.get("security_protocol", "SASL_PLAINTEXT")
        kw["sasl_mechanism"] = kw.get("sasl_mechanism", "PLAIN")
        if auth.username:
            kw["sasl_plain_username"] = auth.username
        if auth.password:
            kw["sasl_plain_password"] = auth.password
    elif t == "sasl_scram_sha_256":
        kw["security_protocol"] = kw.get("security_protocol", "SASL_PLAINTEXT")
        kw["sasl_mechanism"] = "SCRAM-SHA-256"
        if auth.username:
            kw["sasl_plain_username"] = auth.username
        if auth.password:
            kw["sasl_plain_password"] = auth.password
    elif t == "sasl_scram_sha_512":
        kw["security_protocol"] = kw.get("security_protocol", "SASL_PLAINTEXT")
        kw["sasl_mechanism"] = "SCRAM-SHA-512"
        if auth.username:
            kw["sasl_plain_username"] = auth.username
        if auth.password:
            kw["sasl_plain_password"] = auth.password
    elif t == "ssl":
        kw["security_protocol"] = kw.get("security_protocol", "SSL")
        if auth.ssl_cafile:
            kw["ssl_cafile"] = auth.ssl_cafile
        if auth.ssl_certfile:
            kw["ssl_certfile"] = auth.ssl_certfile
        if auth.ssl_keyfile:
            kw["ssl_keyfile"] = auth.ssl_keyfile
    return kw


def _bootstrap(cluster: KafkaClusterSpec) -> str | list[str]:
    bs = cluster.bootstrap_servers or ["localhost:9092"]
    if isinstance(bs, list):
        return ",".join(str(x) for x in bs)
    return str(bs)


def serialize_value(value: Any, spec: SerializersSpec) -> bytes:
    if isinstance(value, bytes):
        return value
    if spec.value == "json" or isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False).encode("utf-8")
    if spec.value == "string":
        return str(value).encode("utf-8")
    if value is None:
        return b""
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def serialize_key(key: Any, spec: SerializersSpec) -> bytes | None:
    if key is None:
        return None
    if isinstance(key, bytes):
        return key
    if spec.key == "json":
        return json.dumps(key, ensure_ascii=False).encode("utf-8")
    return str(key).encode("utf-8")


def deserialize_value(data: bytes | None, spec: SerializersSpec) -> Any:
    if data is None:
        return None
    if spec.value == "bytes":
        return data
    text = data.decode("utf-8", "replace")
    if spec.value == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def deserialize_key(data: bytes | None, spec: SerializersSpec) -> Any:
    if data is None:
        return None
    if spec.key == "bytes":
        return data
    text = data.decode("utf-8", "replace")
    if spec.key == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


async def create_consumer(
    consumer_ref: ResolvedConsumerRef,
    defaults: KafkaDefaults,
    *,
    partitions_override: list[int] | None,
    strategy: ConsumeStrategySpec,
) -> Any:
    from aiokafka import AIOKafkaConsumer

    cluster = consumer_ref.cluster
    spec = consumer_ref.spec
    params = merged_consumer_params(defaults, cluster, spec)
    if strategy.mode in ("earliest", "latest"):
        params["auto_offset_reset"] = strategy.mode
    consumer = AIOKafkaConsumer(
        consumer_ref.topic,
        bootstrap_servers=_bootstrap(cluster),
        group_id=spec.group_id,
        **params,
        **_auth_kwargs(cluster.auth),
    )
    try:
        await consumer.start()
    except BaseException:
        await stop_client(consumer)
        raise
    parts = partitions_override if partitions_override is not None else spec.partitions
    if parts:
        from aiokafka import TopicPartition

        tps = [TopicPartition(consumer_ref.topic, p) for p in parts]
        await consumer.assign(tps)
    return consumer


async def create_producer(
    cluster: KafkaClusterSpec,
    producer_spec: KafkaProducerSpec,
    defaults: KafkaDefaults,
) -> Any:
    from aiokafka import AIOKafkaProducer

    params = merged_producer_params(defaults, cluster, producer_spec)
    producer = AIOKafkaProducer(
        bootstrap_servers=_bootstrap(cluster),
        **params,
        **_auth_kwargs(cluster.auth),
    )
    await producer.start()
    return producer


async def stop_client(client: Any) -> None:
    if client is None:
        return
    try:
        await client.stop()
    except Exception:  # noqa: BLE001
        pass
