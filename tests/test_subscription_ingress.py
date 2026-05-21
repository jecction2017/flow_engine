"""Subscription ingress with memory Kafka transport."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from flow_engine.connectors.backends.kafka.fake_transport import MemoryKafkaTransport
from flow_engine.connectors.registry import reset_registry_for_tests
from flow_engine.db.models import FeDeployRun, FeFlowDeployment, FeWorker
from flow_engine.db.session import db_session
from flow_engine.runner.subscription.ingress import (
    SubscriptionIngressError,
    run_subscription_ingress,
)
from tests.kafka_memory_fixtures import MEMORY_CONSUMER_ID, MEMORY_KAFKA_DICT


_MINIMAL_FLOW = {
    "display_name": "sub_test",
    "version": "1",
    "strategies": {"s": {"name": "s", "mode": "sync"}},
    "nodes": [
        {
            "name": "t",
            "id": "t",
            "type": "task",
            "strategy_ref": "s",
            "script": '{"ok": resolve("$.global.alert.id")}',
            "boundary": {"outputs": {"ok": "$.global.ok"}},
        }
    ],
}


@pytest.mark.asyncio
async def test_subscription_ingress_creates_deploy_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()

    import json as _json

    flow_data = _MINIMAL_FLOW

    with db_session() as s:
        from flow_engine.db.models import FeFlow, FeFlowVersion

        s.add(FeFlow(flow_code="sub_flow", display_name="sub", latest_ver_no=1, has_draft=False))
        s.add(
            FeFlowVersion(
                flow_code="sub_flow",
                ver_no=1,
                body=_json.dumps(flow_data),
                display_name="sub_test",
                description="",
            )
        )
        dep = FeFlowDeployment(
            flow_code="sub_flow",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={
                "subscription": {
                    "consumer_id": MEMORY_CONSUMER_ID,
                },
                "consumption": {"batch_max_records": 10, "poll_timeout_ms": 200},
                "dispatch": {"max_in_flight": 4},
                "parse": {
                    "codec": "json",
                    "transform": "mapping",
                    "mapping": {"mode": "spread"},
                },
            },
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(dep)
        s.flush()
        dep_id = int(dep.id)
        s.add(
            FeWorker(
                worker_id="w1",
                host="h",
                pid=1,
                status="active",
                last_heartbeat=datetime.now(timezone.utc),
                capabilities={},
            )
        )

    alert = {
        "id": "ALT-1",
        "severity": "HIGH",
        "indicators": [],
    }
    await MemoryKafkaTransport.publish(
        "alerts",
        json.dumps({"alert": alert}).encode("utf-8"),
    )
    await MemoryKafkaTransport.publish(
        "alerts",
        json.dumps({"alert": {**alert, "id": "ALT-2"}}).encode("utf-8"),
    )

    stop = asyncio.Event()
    deployment = {
        "id": dep_id,
        "flow_code": "sub_flow",
        "ver_no": 1,
        "mode": "production",
        "schedule_type": "subscription",
        "schedule_config": {
            "subscription": {
                "consumer_id": MEMORY_CONSUMER_ID,
            },
            "consumption": {"batch_max_records": 10, "poll_timeout_ms": 200},
            "dispatch": {"max_in_flight": 4},
            "parse": {
                "codec": "json",
                "transform": "mapping",
                "mapping": {"mode": "spread"},
            },
        },
        "capability_policy": [],
        "env_profile_code": "default",
        "observability": {},
    }

    from flow_engine.runner.worker import Worker, _subscription_trigger_type

    worker = Worker(worker_id="w1", max_concurrent_flows=4)

    async def _prepare(deploy: dict, trigger_context: dict | None):
        return await worker._prepare_runtime(  # noqa: SLF001
            deploy,
            trigger_context=trigger_context,
            trigger_type=_subscription_trigger_type(deploy),
        )

    def _tree_copy(_profile: str) -> dict:
        return MEMORY_KAFKA_DICT

    monkeypatch.setattr("flow_engine.stores.data_dict.tree_copy", _tree_copy)

    async def _run_briefly() -> None:
        task = asyncio.create_task(
            run_subscription_ingress(
                deployment,
                stop_evt=stop,
                prepare_runtime=_prepare,
                worker_id="w1",
            )
        )
        await asyncio.sleep(1.5)
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)

    await _run_briefly()

    with db_session() as s:
        rows = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == dep_id)
            ).scalars().all()
        )
        run_meta = [
            (int(r.id), r.trigger_context, r.trigger_type, r.status) for r in rows
        ]
    assert len(run_meta) >= 2
    assert all(tc is not None for _, tc, _, _ in run_meta)
    assert run_meta[0][2] == "subscription"


@pytest.mark.asyncio
async def test_session_open_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()

    deployment = {
        "id": 99,
        "flow_code": "sub_flow",
        "ver_no": 1,
        "mode": "production",
        "schedule_type": "subscription",
        "schedule_config": {
            "subscription": {"consumer_id": "memory.alerts.nonexistent_consumer"},
            "consumption": {"batch_max_records": 1, "poll_timeout_ms": 100},
            "dispatch": {"max_in_flight": 1},
        },
        "capability_policy": [],
        "env_profile_code": "default",
    }

    def _tree_copy(_profile: str) -> dict:
        return MEMORY_KAFKA_DICT

    monkeypatch.setattr("flow_engine.stores.data_dict.tree_copy", _tree_copy)

    stop = asyncio.Event()

    async def _prepare(_deploy: dict, _trigger: dict | None):
        raise AssertionError("prepare_runtime should not run")

    with pytest.raises(SubscriptionIngressError) as exc_info:
        await run_subscription_ingress(
            deployment,
            stop_evt=stop,
            prepare_runtime=_prepare,
            worker_id="w1",
        )
    assert exc_info.value.error.get("code") == "CONSUMER_NOT_FOUND"


@pytest.mark.asyncio
async def test_subscription_ingress_sequential_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Messages produced after ingress starts must each create a deploy run."""
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()

    import json as _json

    with db_session() as s:
        from flow_engine.db.models import FeFlow, FeFlowVersion

        s.add(FeFlow(flow_code="sub_seq", display_name="sub", latest_ver_no=1, has_draft=False))
        s.add(
            FeFlowVersion(
                flow_code="sub_seq",
                ver_no=1,
                body=_json.dumps(_MINIMAL_FLOW),
                display_name="sub_seq",
                description="",
            )
        )
        dep = FeFlowDeployment(
            flow_code="sub_seq",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={
                "subscription": {"consumer_id": MEMORY_CONSUMER_ID},
                "consumption": {"batch_max_records": 10, "poll_timeout_ms": 200},
                "dispatch": {"max_in_flight": 8},
                "parse": {
                    "codec": "json",
                    "transform": "mapping",
                    "mapping": {"mode": "spread"},
                },
            },
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(dep)
        s.flush()
        dep_id = int(dep.id)
        schedule_config = {
            "subscription": {"consumer_id": MEMORY_CONSUMER_ID},
            "consumption": {"batch_max_records": 10, "poll_timeout_ms": 200},
            "dispatch": {"max_in_flight": 8},
            "parse": {
                "codec": "json",
                "transform": "mapping",
                "mapping": {"mode": "spread"},
            },
        }

    deployment = {
        "id": dep_id,
        "flow_code": "sub_seq",
        "ver_no": 1,
        "mode": "production",
        "schedule_type": "subscription",
        "schedule_config": schedule_config,
        "capability_policy": [],
        "env_profile_code": "default",
        "observability": {},
    }

    from flow_engine.runner.worker import Worker, _subscription_trigger_type

    worker = Worker(worker_id="w1", max_concurrent_flows=4)

    async def _prepare(deploy: dict, trigger_context: dict | None):
        return await worker._prepare_runtime(  # noqa: SLF001
            deploy,
            trigger_context=trigger_context,
            trigger_type=_subscription_trigger_type(deploy),
        )

    def _tree_copy(_profile: str) -> dict:
        return MEMORY_KAFKA_DICT

    monkeypatch.setattr("flow_engine.stores.data_dict.tree_copy", _tree_copy)

    stop = asyncio.Event()

    async def _publish_one(msg_id: str) -> None:
        await MemoryKafkaTransport.publish(
            "alerts",
            json.dumps({"alert": {"id": msg_id}}).encode("utf-8"),
        )

    task = asyncio.create_task(
        run_subscription_ingress(
            deployment,
            stop_evt=stop,
            prepare_runtime=_prepare,
            worker_id="w1",
        )
    )
    try:
        await _publish_one("SEQ-1")
        await asyncio.sleep(0.8)
        await _publish_one("SEQ-2")
        await asyncio.sleep(0.8)
        await _publish_one("SEQ-3")
        await asyncio.sleep(0.8)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5.0)

    with db_session() as s:
        rows = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == dep_id)
            ).scalars().all()
        )
    assert len(rows) >= 3


@pytest.mark.asyncio
async def test_registry_rebind_same_config_does_not_close_subscription_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FlowRuntime.run binds registry again; must not LeaveGroup the ingress session."""
    reset_registry_for_tests()
    MemoryKafkaTransport.reset_all()

    def _tree_copy(_profile: str) -> dict:
        return MEMORY_KAFKA_DICT

    monkeypatch.setattr("flow_engine.stores.data_dict.tree_copy", _tree_copy)

    from flow_engine.connectors.registry import get_registry
    from flow_engine.runner.subscription.kafka_session import ConnectorSubscriptionSession

    reg = get_registry()
    reg.bind(MEMORY_KAFKA_DICT, profile="default")
    handle = reg.get("kafka", "memory")
    open_result = handle.execute(
        "session_open",
        session_key="deploy-test",
        consumer_id=MEMORY_CONSUMER_ID,
    )
    assert open_result.get("ok"), open_result
    session = ConnectorSubscriptionSession(
        handle,
        session_key="deploy-test",
        consumer_id=MEMORY_CONSUMER_ID,
    )

    await MemoryKafkaTransport.publish(
        "alerts",
        json.dumps({"alert": {"id": "RB-1"}}).encode("utf-8"),
    )
    batch1 = await session.poll(max_records=10, timeout_ms=500)
    assert len(batch1) >= 1

    # Simulate FlowRuntime.run() rebinding without profile (used to close_all).
    reg.bind(MEMORY_KAFKA_DICT, profile=None)

    await MemoryKafkaTransport.publish(
        "alerts",
        json.dumps({"alert": {"id": "RB-2"}}).encode("utf-8"),
    )
    batch2 = await session.poll(max_records=10, timeout_ms=500)
    assert len(batch2) >= 1
    await session.close()
