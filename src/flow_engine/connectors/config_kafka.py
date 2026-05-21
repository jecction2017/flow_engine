"""Pydantic schemas for Kafka configuration in the data dictionary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from flow_engine.connectors.config import ProtectionSpec


class KafkaAuthSpec(BaseModel):
    type: Literal[
        "none",
        "plain",
        "sasl_plain",
        "sasl_plaintext",
        "sasl_scram_sha_256",
        "sasl_scram_sha_512",
        "ssl",
    ] = "none"
    username: str | None = None
    password: str | None = None
    security_protocol: str | None = None
    sasl_mechanism: str | None = None
    ssl_cafile: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None


class SerializersSpec(BaseModel):
    key: Literal["string", "bytes", "json"] = "bytes"
    value: Literal["string", "bytes", "json"] = "bytes"


class ConsumeStrategySpec(BaseModel):
    mode: Literal["default", "earliest", "latest", "offset", "timestamp"] = "default"
    offsets: dict[int, int] | None = None
    timestamp_ms: int | None = None

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> ConsumeStrategySpec:
        if self.mode == "offset" and not self.offsets:
            raise ValueError("strategy.offsets required when mode is 'offset'")
        if self.mode == "timestamp" and self.timestamp_ms is None:
            raise ValueError("strategy.timestamp_ms required when mode is 'timestamp'")
        return self


class KafkaConsumerSpec(BaseModel):
    group_id: str = Field(..., min_length=1)
    serializers: SerializersSpec = Field(default_factory=SerializersSpec)
    strategy: ConsumeStrategySpec | str = Field(default_factory=ConsumeStrategySpec)
    partitions: list[int] | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("strategy", mode="before")
    @classmethod
    def _coerce_strategy(cls, v: Any) -> Any:
        if isinstance(v, str):
            return ConsumeStrategySpec(mode=v)  # type: ignore[arg-type]
        return v


class KafkaProducerSpec(BaseModel):
    serializers: SerializersSpec = Field(default_factory=SerializersSpec)
    params: dict[str, Any] = Field(default_factory=dict)


class KafkaTopicSpec(BaseModel):
    consumers: dict[str, KafkaConsumerSpec] = Field(default_factory=dict)
    producers: dict[str, KafkaProducerSpec] = Field(default_factory=dict)


class KafkaClusterSpec(BaseModel):
    bootstrap_servers: list[str] | str | None = None
    auth: KafkaAuthSpec = Field(default_factory=KafkaAuthSpec)
    transport: Literal["kafka", "memory"] = "kafka"
    topics: dict[str, KafkaTopicSpec] = Field(default_factory=dict)
    protection: ProtectionSpec | None = None

    @field_validator("bootstrap_servers", mode="before")
    @classmethod
    def _coerce_bootstrap(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def _validate_transport(self) -> KafkaClusterSpec:
        if self.transport == "kafka" and not self.bootstrap_servers:
            raise ValueError("bootstrap_servers required when transport is 'kafka'")
        return self


class KafkaDefaults(BaseModel):
    protection: ProtectionSpec = Field(default_factory=ProtectionSpec)
    consumer_params: dict[str, Any] = Field(default_factory=dict)
    producer_params: dict[str, Any] = Field(default_factory=dict)
    request_timeout_sec: float = Field(default=30.0, ge=1.0, le=600.0)


class KafkaConfig(BaseModel):
    defaults: KafkaDefaults = Field(default_factory=KafkaDefaults)
    instances: dict[str, KafkaClusterSpec] = Field(default_factory=dict)

    @field_validator("instances")
    @classmethod
    def _non_empty_ids(cls, v: dict[str, KafkaClusterSpec]) -> dict[str, KafkaClusterSpec]:
        for key in v:
            if not key.strip():
                raise ValueError("instance id must be non-empty")
        return v


@dataclass
class ResolvedConsumerRef:
    """Flattened consumer binding after bind."""

    consumer_id: str
    cluster_id: str
    topic: str
    name: str
    spec: KafkaConsumerSpec
    cluster: KafkaClusterSpec


@dataclass
class ResolvedProducerRef:
    producer_id: str
    cluster_id: str
    topic: str
    name: str
    spec: KafkaProducerSpec
    cluster: KafkaClusterSpec


def parse_kafka_config(raw: Any) -> KafkaConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    return KafkaConfig.model_validate(raw)


def build_kafka_indexes(
    cfg: KafkaConfig,
) -> tuple[dict[str, ResolvedConsumerRef], dict[str, ResolvedProducerRef]]:
    consumers: dict[str, ResolvedConsumerRef] = {}
    producers: dict[str, ResolvedProducerRef] = {}
    for cluster_id, cluster in cfg.instances.items():
        for topic_name, topic in cluster.topics.items():
            for cname, cspec in topic.consumers.items():
                cid = f"{cluster_id}.{topic_name}.{cname}"
                consumers[cid] = ResolvedConsumerRef(
                    consumer_id=cid,
                    cluster_id=cluster_id,
                    topic=topic_name,
                    name=cname,
                    spec=cspec,
                    cluster=cluster,
                )
            for pname, pspec in topic.producers.items():
                pid = f"{cluster_id}.{topic_name}.{pname}"
                producers[pid] = ResolvedProducerRef(
                    producer_id=pid,
                    cluster_id=cluster_id,
                    topic=topic_name,
                    name=pname,
                    spec=pspec,
                    cluster=cluster,
                )
    return consumers, producers


def parse_consumer_id(consumer_id: str) -> tuple[str, str, str]:
    parts = consumer_id.split(".", 2)
    if len(parts) != 3:
        raise ValueError(
            f"consumer_id must be cluster.topic.consumer, got {consumer_id!r}"
        )
    return parts[0], parts[1], parts[2]
