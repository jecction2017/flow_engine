"""Kafka Starlark builtins with memory transport."""

from __future__ import annotations

import json

import pytest

from flow_engine.connectors.backends.kafka.fake_transport import MemoryKafkaTransport
from flow_engine.connectors.registry import reset_registry_for_tests
from flow_engine.starlark_sdk.integrations.kafka_builtins import kafka_receive, kafka_send
from tests.kafka_memory_fixtures import (
    MEMORY_CONSUMER_ID,
    MEMORY_DLQ_PRODUCER_ID,
    MEMORY_KAFKA_DICT,
)


@pytest.fixture(autouse=True)
def _reset_kafka() -> None:
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()
    from flow_engine.connectors.registry import get_registry
    from flow_engine.stores.data_dict import dictionary_scope

    with dictionary_scope(MEMORY_KAFKA_DICT):
        get_registry().bind(MEMORY_KAFKA_DICT)
    yield
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()


def test_kafka_receive_bounded() -> None:
    import asyncio

    async def _pub() -> None:
        await MemoryKafkaTransport.publish(
            "alerts",
            json.dumps({"id": "m1"}).encode(),
        )

    asyncio.get_event_loop().run_until_complete(_pub())

    from flow_engine.stores.data_dict import dictionary_scope
    from flow_engine.connectors.registry import get_registry

    with dictionary_scope(MEMORY_KAFKA_DICT):
        get_registry().bind(MEMORY_KAFKA_DICT)
        out = kafka_receive(MEMORY_CONSUMER_ID, max_records=5, timeout_ms=500)

    assert out["ok"] is True
    messages = out["data"]["messages"]
    assert len(messages) >= 1
    assert messages[0]["value"]["id"] == "m1"


def test_kafka_send() -> None:
    from flow_engine.stores.data_dict import dictionary_scope
    from flow_engine.connectors.registry import get_registry

    with dictionary_scope(MEMORY_KAFKA_DICT):
        get_registry().bind(MEMORY_KAFKA_DICT)
        out = kafka_send(MEMORY_DLQ_PRODUCER_ID, {"err": "x"}, key="k1")

    assert out["ok"] is True
    assert "offset" in out["data"]
