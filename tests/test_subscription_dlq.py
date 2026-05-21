"""DLQ publish via Kafka connector producer_id."""

from __future__ import annotations

import asyncio
import json

import pytest

from flow_engine.connectors.backends.kafka.fake_transport import MemoryKafkaTransport
from flow_engine.connectors.backends.kafka.messages import BusMessage, Position
from flow_engine.connectors.registry import get_registry, reset_registry_for_tests
from flow_engine.runner.subscription.ingress import _handle_poison
from flow_engine.runner.subscription.spec import (
    ConsumptionSection,
    DispatchSection,
    ParseSection,
    SubscriptionSection,
    SubscriptionSpec,
)
from tests.kafka_memory_fixtures import (
    MEMORY_CONSUMER_ID,
    MEMORY_DLQ_PRODUCER_ID,
    MEMORY_KAFKA_DICT,
)


@pytest.mark.asyncio
async def test_dlq_publish_uses_producer_id() -> None:
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()

    reg = get_registry()
    reg.bind(MEMORY_KAFKA_DICT)
    handle = reg.get("kafka", "memory")

    spec = SubscriptionSpec(
        subscription=SubscriptionSection(
            consumer_id=MEMORY_CONSUMER_ID,
            producer_id=MEMORY_DLQ_PRODUCER_ID,
        ),
        consumption=ConsumptionSection(
            dlq={"producer_id": MEMORY_DLQ_PRODUCER_ID},
        ),
        dispatch=DispatchSection(),
        parse=ParseSection(),
    )
    msg = BusMessage(
        topic="alerts",
        partition=0,
        offset=7,
        key=None,
        value=b'{"alert":{"id":"X"}}',
    )

    class _Session:
        committed: list = []

        async def commit(self, positions):  # noqa: ANN001
            self.committed.extend(positions)

    session = _Session()
    sub = spec.subscription
    pos = Position(topic="alerts", partition=0, offset=7)
    await _handle_poison(spec, msg, session, handle, sub, pos, error="boom")

    async with MemoryKafkaTransport._lock:
        st = MemoryKafkaTransport._topics.get("alerts_dlq")
        assert st is not None
        assert len(st.messages) == 1
        body = json.loads(st.messages[0].value.decode())
        assert body["error"] == "boom"
        assert body["source_topic"] == "alerts"
        assert body["offset"] == 7
    assert len(session.committed) == 1
