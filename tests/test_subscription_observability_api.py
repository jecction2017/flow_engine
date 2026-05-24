"""HTTP API for subscription message ledger observability."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from flow_engine.runner.subscription.dedup import begin_message_processing, finish_message_processing


@pytest.fixture
def client() -> TestClient:
    import flow_engine.lookup.lookup_store as lookup_mod
    import flow_engine.stores.data_dict as dict_mod
    import flow_engine.stores.profile_store as profile_mod

    dict_mod.invalidate_store_cache()
    profile_mod.invalidate_profile_store_cache()
    lookup_mod.invalidate_lookup_store_cache()

    from flow_engine.api.http_api import create_app

    return TestClient(create_app())


def _create_subscription_deployment(client, flow_code: str = "sub_obs_flow") -> int:
    from tests.test_runner_api import _commit_flow

    ver = _commit_flow(client, flow_code)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": flow_code,
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "subscription",
            "schedule_config": {
                "subscription": {"consumer_id": "memory.alerts.default"},
                "consumption": {},
                "dispatch": {"max_in_flight": 4},
                "parse": {"codec": "json", "transform": "mapping", "mapping": {"mode": "spread"}},
            },
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def test_subscription_summary_and_messages(client) -> None:
    dep_id = _create_subscription_deployment(client)

    begin_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=10,
        window_s=None,
        idempotency=False,
    )
    finish_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=10,
        status="failed",
        error="bad json",
    )
    begin_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=11,
        window_s=None,
        idempotency=False,
    )
    finish_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=11,
        status="completed",
        deploy_run_id=None,
    )

    r = client.get(f"/api/deployments/{dep_id}/subscription/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deployment_id"] == dep_id
    assert body["messages"]["total"] == 2
    assert body["messages"]["by_status"]["failed"] == 1
    assert body["messages"]["by_status"]["completed"] == 1
    assert len(body["recent_failed_messages"]) == 1
    assert body["recent_failed_messages"][0]["offset"] == 10

    r = client.get(
        f"/api/deployments/{dep_id}/subscription/messages",
        params={"status": "failed", "limit": 10},
    )
    assert r.status_code == 200, r.text
    listed = r.json()
    assert listed["total"] == 1
    assert listed["messages"][0]["status"] == "failed"
    assert "bad json" in (listed["messages"][0]["error"] or "")
    assert body["messages"]["failed_recent"] == 1
    # Latest ledger row is completed (offset 11) after the failure — alert cleared.
    assert body["messages"]["failure_alert"] is False


def test_subscription_summary_failure_alert_active_while_failing(client) -> None:
    dep_id = _create_subscription_deployment(client, "sub_alert_active")

    begin_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=30,
        window_s=None,
        idempotency=False,
    )
    finish_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=30,
        status="failed",
        error="still broken",
    )

    r = client.get(f"/api/deployments/{dep_id}/subscription/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["messages"]["failure_alert"] is True
    assert body["messages"]["failed_recent"] == 1


def test_subscription_summary_failure_alert_clears_after_recovery(client) -> None:
    dep_id = _create_subscription_deployment(client, "sub_recover_flow")

    begin_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=20,
        window_s=None,
        idempotency=False,
    )
    finish_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=20,
        status="failed",
        error="transient",
    )
    begin_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=21,
        window_s=None,
        idempotency=False,
    )
    finish_message_processing(
        deployment_id=dep_id,
        topic="alerts",
        partition=0,
        offset=21,
        status="completed",
        deploy_run_id=None,
    )

    r = client.get(f"/api/deployments/{dep_id}/subscription/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["messages"]["by_status"]["failed"] == 1
    assert body["messages"]["failed_recent"] == 1
    assert body["messages"]["failure_alert"] is False
    assert len(body["recent_failed_messages"]) == 1


def test_recent_failed_subscription_messages_dedup_per_deployment(client) -> None:
    dep_a = _create_subscription_deployment(client, "sub_fail_a")
    dep_b = _create_subscription_deployment(client, "sub_fail_b")

    for dep_id, offsets in ((dep_a, (1, 2)), (dep_b, (3,))):
        for offset in offsets:
            begin_message_processing(
                deployment_id=dep_id,
                topic="alerts",
                partition=0,
                offset=offset,
                window_s=None,
                idempotency=False,
            )
            finish_message_processing(
                deployment_id=dep_id,
                topic="alerts",
                partition=0,
                offset=offset,
                status="failed",
                error=f"err-{offset}",
            )

    r = client.get("/api/subscription/recent-failed-messages", params={"hours": 24})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    dep_ids = {m["deployment_id"] for m in body["messages"]}
    assert dep_ids == {dep_a, dep_b}
    by_dep = {m["deployment_id"]: m for m in body["messages"]}
    assert by_dep[dep_a]["offset"] == 2
    assert by_dep[dep_b]["offset"] == 3

    r = client.get(
        "/api/subscription/recent-failed-messages",
        params={"hours": 24, "offset": 0, "limit": 1},
    )
    assert r.status_code == 200, r.text
    page1 = r.json()
    assert page1["total"] == 2
    assert len(page1["messages"]) == 1

    r = client.get(
        "/api/subscription/recent-failed-messages",
        params={"hours": 24, "offset": 1, "limit": 1},
    )
    assert r.status_code == 200, r.text
    page2 = r.json()
    assert len(page2["messages"]) == 1
    assert page1["messages"][0]["deployment_id"] != page2["messages"][0]["deployment_id"]


def test_subscription_observability_rejects_non_subscription(client) -> None:
    from tests.test_runner_api import _commit_flow

    ver = _commit_flow(client, "once_obs_flow")
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "once_obs_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    dep_id = int(r.json()["id"])
    r = client.get(f"/api/deployments/{dep_id}/subscription/summary")
    assert r.status_code == 400
