"""Subscription message ledger (fe_subscription_dedup) without idempotency."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from flow_engine.connectors.backends.kafka.fake_transport import MemoryKafkaTransport
from flow_engine.connectors.backends.kafka.messages import BusMessage
from flow_engine.connectors.registry import get_registry, reset_registry_for_tests
from flow_engine.db.models import FeFlowDeployment, FeSubscriptionDedup
from flow_engine.db.session import db_session
from flow_engine.runner.subscription.dedup import (
    begin_message_processing,
    finish_message_processing,
)
from flow_engine.runner.subscription.ingress import _process_one
from flow_engine.runner.subscription.spec import (
    ConsumptionSection,
    DispatchSection,
    ParseSection,
    SubscriptionSection,
    SubscriptionSpec,
)
from tests.kafka_memory_fixtures import MEMORY_CONSUMER_ID, MEMORY_KAFKA_DICT


@pytest.mark.asyncio
async def test_invalid_json_records_failed_without_idempotency() -> None:
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()

    with db_session() as s:
        dep = FeFlowDeployment(
            flow_code="ledger_flow",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={},
            worker_policy={},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(dep)
        s.flush()
        dep_id = int(dep.id)

    spec = SubscriptionSpec(
        subscription=SubscriptionSection(consumer_id=MEMORY_CONSUMER_ID),
        consumption=ConsumptionSection(),
        dispatch=DispatchSection(),
        parse=ParseSection(codec="json", transform="mapping", mapping={"mode": "spread"}),
    )
    deployment = {
        "id": dep_id,
        "mode": "production",
        "capability_policy": [],
    }
    msg = BusMessage(topic="alerts", partition=0, offset=33, key=None, value=b"not-json")

    reg = get_registry()
    reg.bind(MEMORY_KAFKA_DICT)
    handle = reg.get("kafka", "memory")

    class _Session:
        committed: list = []

        async def commit(self, positions):  # noqa: ANN001
            self.committed.extend(positions)

    session = _Session()
    sem = asyncio.Semaphore(1)

    async def _prepare(_deploy: dict, _trigger: dict | None):
        raise AssertionError("prepare_runtime must not run for invalid payload")

    await _process_one(
        deployment,
        spec=spec,
        msg=msg,
        session=session,
        handle=handle,
        sub=spec.subscription,
        prepare_runtime=_prepare,
        sem=sem,
    )

    with db_session() as s:
        row = s.execute(
            select(FeSubscriptionDedup).where(
                FeSubscriptionDedup.deployment_id == dep_id,
                FeSubscriptionDedup.position_key == "alerts:0:33",
            )
        ).scalar_one()
        status = row.status
        error = row.error
        run_id = row.deploy_run_id
    assert status == "failed"
    assert error is not None
    assert "UTF-8 JSON" in error or "Expecting value" in error
    assert run_id is None
    assert len(session.committed) == 1


def test_begin_without_idempotency_upserts_processing() -> None:
    with db_session() as s:
        dep = FeFlowDeployment(
            flow_code="ledger_upsert",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={},
            worker_policy={},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(dep)
        s.flush()
        dep_id = int(dep.id)

    assert begin_message_processing(
        deployment_id=dep_id,
        topic="t",
        partition=1,
        offset=9,
        window_s=None,
        idempotency=False,
    )
    finish_message_processing(
        deployment_id=dep_id,
        topic="t",
        partition=1,
        offset=9,
        status="failed",
        error="parse boom",
    )
    assert begin_message_processing(
        deployment_id=dep_id,
        topic="t",
        partition=1,
        offset=9,
        window_s=None,
        idempotency=False,
    )
    with db_session() as s:
        row = s.execute(
            select(FeSubscriptionDedup).where(
                FeSubscriptionDedup.deployment_id == dep_id,
                FeSubscriptionDedup.position_key == "t:1:9",
            )
        ).scalar_one()
        status = row.status
        error = row.error
    assert status == "processing"
    assert error is None
