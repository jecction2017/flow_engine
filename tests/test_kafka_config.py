"""Kafka dictionary config validation."""

from __future__ import annotations

import pytest

from flow_engine.connectors.config_kafka import (
    ConsumeStrategySpec,
    KafkaConfig,
    build_kafka_indexes,
    parse_consumer_id,
    parse_kafka_config,
)


def test_parse_kafka_config_hierarchy() -> None:
    raw = {
        "defaults": {"consumer_params": {"enable_auto_commit": False}},
        "instances": {
            "memory": {
                "transport": "memory",
                "topics": {
                    "alerts": {
                        "consumers": {
                            "ingress": {
                                "group_id": "g1",
                                "strategy": "earliest",
                            }
                        },
                        "producers": {"dlq": {}},
                    }
                },
            }
        },
    }
    cfg = parse_kafka_config(raw)
    assert cfg is not None
    consumers, producers = build_kafka_indexes(cfg)
    assert "memory.alerts.ingress" in consumers
    assert "memory.alerts.dlq" in producers
    assert consumers["memory.alerts.ingress"].spec.group_id == "g1"


def test_offset_strategy_requires_offsets() -> None:
    with pytest.raises(ValueError, match="offsets"):
        ConsumeStrategySpec(mode="offset")


def test_parse_consumer_id() -> None:
    assert parse_consumer_id("a.b.c") == ("a", "b", "c")
    with pytest.raises(ValueError):
        parse_consumer_id("invalid")
