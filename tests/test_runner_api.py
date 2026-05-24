"""HTTP integration tests for runner-layer endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


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


def _commit_flow(client: TestClient, flow_id: str = "runner_flow") -> int:
    body: dict[str, Any] = {
        "display_name": flow_id,
        "version": "1.0.0",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [
            {
                "id": "n1",
                "type": "task",
                "strategy_ref": "default_sync",
                "script": '{"out": "ok"}',
                "boundary": {"outputs": {"out": "$.global.r"}},
            }
        ],
    }
    r = client.post("/api/flows", json={"id": flow_id, "display_name": flow_id})
    assert r.status_code == 200
    r = client.put(f"/api/flows/{flow_id}/draft", json=body)
    assert r.status_code == 200
    r = client.post(f"/api/flows/{flow_id}/versions", json={})
    assert r.status_code == 200
    return int(r.json()["version"])


def test_create_and_list_deployment(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    dep = r.json()
    assert dep["status"] == "pending"
    assert dep["schedule_type"] == "once"
    assert dep["created_at"].endswith("Z")

    r = client.get("/api/deployments")
    assert r.status_code == 200
    rows = r.json()["deployments"]
    assert any(d["id"] == dep["id"] for d in rows)
    assert next(d for d in rows if d["id"] == dep["id"])["created_at"].endswith("Z")


def test_create_deployment_without_auto_start(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
            "auto_start": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "stopped"


def test_list_deployments_root_only_hides_legacy_children(client: TestClient) -> None:
    from flow_engine.db.models import FeFlowDeployment
    from flow_engine.db.session import db_session

    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    root_id = int(r.json()["id"])
    with db_session() as s:
        s.add(
            FeFlowDeployment(
                flow_code="runner_flow",
                ver_no=ver,
                mode="production",
                schedule_type="once",
                schedule_config={},
                worker_policy={"type": "single_active", "target_workers": 1},
                capability_policy=[],
                worker_targeting={},
                status="failed",
                env_profile_code="default",
                parent_deployment_id=root_id,
            )
        )

    r_all = client.get("/api/deployments")
    assert r_all.status_code == 200
    n_all = len(r_all.json()["deployments"])

    r_root = client.get("/api/deployments?root_only=true")
    assert r_root.status_code == 200
    ids = {d["id"] for d in r_root.json()["deployments"]}
    assert root_id in ids
    assert n_all >= len(ids) + 1


def test_get_system_default_capability_policy(client: TestClient) -> None:
    r = client.get("/api/capabilities/system-default-policy")
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) == {"debug", "shadow", "production"}

    for mode in ("debug", "shadow"):
        rules = data[mode]
        cats = {r.get("builtin_category") for r in rules}
        actions = {r.get("action") for r in rules}
        assert {"integration", "db_write", "mq_publish"}.issubset(cats)
        assert actions == {"suppress"}

    assert data["production"] == []


def test_profile_system_policy_roundtrip_per_mode(client: TestClient) -> None:
    # write per-mode map
    put = client.put(
        "/api/profiles/default/system-policy",
        json={
            "system_capability_policy": {
                "debug": [{"builtin_category": "integration", "builtin_name": None, "action": "suppress", "redirect_params": {}}],
                "shadow": [],
                "production": [{"builtin_category": "integration", "builtin_name": None, "action": "allow", "redirect_params": {}}],
            }
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["ok"] is True
    assert set(body["system_capability_policy"].keys()) == {"debug", "shadow", "production"}

    get = client.get("/api/profiles/default/system-policy")
    assert get.status_code == 200, get.text
    got = get.json()["system_capability_policy"]
    assert set(got.keys()) == {"debug", "shadow", "production"}
    assert got["debug"][0]["action"] == "suppress"
    assert got["production"][0]["action"] == "allow"


def test_profile_system_policy_backward_compatible_list(client: TestClient) -> None:
    # legacy shape: list[rule] is accepted and normalized to all modes
    put = client.put(
        "/api/profiles/default/system-policy",
        json={
            "system_capability_policy": [
                {"builtin_category": "integration", "builtin_name": None, "action": "suppress", "redirect_params": {}}
            ]
        },
    )
    assert put.status_code == 200, put.text
    got = put.json()["system_capability_policy"]
    assert got["debug"][0]["action"] == "suppress"
    assert got["shadow"][0]["action"] == "suppress"
    assert got["production"][0]["action"] == "suppress"


def test_create_subscription_deployment(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "subscription",
            "schedule_config": {
                "subscription": {
                    "consumer_id": "memory.alerts.default",
                },
                "parse": {
                    "codec": "json",
                    "transform": "mapping",
                    "mapping": {"mode": "spread"},
                },
            },
            "worker_policy": {"type": "multi_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200
    assert r.json()["schedule_type"] == "subscription"


def test_create_cron_requires_cron_expr(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "cron",
            "schedule_config": {},  # missing cron_expr
            "worker_policy": {},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 400


def test_create_cron_with_auto_start_false_is_stopped(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "cron",
            "schedule_config": {"cron_expr": "0 8 * * *"},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
            "auto_start": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "stopped"


def test_create_cron_default_auto_start_is_running(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "cron",
            "schedule_config": {"cron_expr": "0 8 * * *"},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"


def test_create_deployment_invalid_flow_version(client: TestClient) -> None:
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "nonexistent_flow",
            "ver_no": 99,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 400
    assert "flow version not found" in r.json()["detail"]


def test_patch_pending_clears_stale_assignments(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    from flow_engine.db.models import FeFlowDeployment, FeWorkerAssignment
    from flow_engine.db.session import db_session

    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "schedule_type": "once",
        },
    )
    dep_id = r.json()["id"]
    with db_session() as s:
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="orphan_w",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
        )
        dep = s.get(FeFlowDeployment, dep_id)
        dep.status = "failed"
        dep.status_detail = {"reason": "subscription_ingress_failed", "message": "test"}

    r = client.patch(f"/api/deployments/{dep_id}", json={"status": "pending"})
    assert r.status_code == 200
    r = client.get(f"/api/deployments/{dep_id}")
    body = r.json()
    assert body["status"] == "pending"
    assert body["status_detail"] is None
    assert body["assignments"] == []


def test_patch_deployment_config_requires_stopped(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "auto_start": True,
        },
    )
    assert r.status_code == 200, r.text
    dep_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = client.patch(
        f"/api/deployments/{dep_id}",
        json={
            "config": {
                "flow_code": "runner_flow",
                "ver_no": ver,
                "mode": "shadow",
                "schedule_type": "once",
                "schedule_config": {},
                "worker_policy": {"type": "single_active", "target_workers": 1},
                "capability_policy": [],
                "env_profile_code": "default",
                "worker_targeting": {"mode": "any"},
            }
        },
    )
    assert r.status_code == 409
    assert "stopped" in r.json()["detail"].lower()

    r = client.patch(f"/api/deployments/{dep_id}", json={"status": "stopping"})
    assert r.status_code == 200


def test_patch_deployment_config_updates_fields(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "cron",
            "schedule_config": {"cron_expr": "0 * * * *"},
            "auto_start": False,
        },
    )
    assert r.status_code == 200, r.text
    dep_id = r.json()["id"]
    assert r.json()["status"] == "stopped"

    r = client.patch(
        f"/api/deployments/{dep_id}",
        json={
            "config": {
                "flow_code": "runner_flow",
                "ver_no": ver,
                "mode": "shadow",
                "schedule_type": "cron",
                "schedule_config": {"cron_expr": "0 */10 * * *"},
                "worker_policy": {"type": "single_active", "target_workers": 2},
                "capability_policy": [],
                "env_profile_code": "default",
                "worker_targeting": {"mode": "any"},
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "shadow"
    assert body["schedule_config"]["cron_expr"] == "0 */10 * * *"
    assert body["worker_policy"]["target_workers"] == 2
    assert body["status"] == "stopped"

    r = client.get(f"/api/deployments/{dep_id}")
    assert r.json()["mode"] == "shadow"


def test_patch_and_delete_deployment(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "schedule_type": "once",
        },
    )
    assert r.status_code == 200
    dep_id = r.json()["id"]

    r = client.patch(f"/api/deployments/{dep_id}", json={"status": "stopping"})
    assert r.status_code == 200
    assert r.json()["status"] == "stopping"

    r = client.delete(f"/api/deployments/{dep_id}")
    assert r.status_code == 200
    r = client.get(f"/api/deployments/{dep_id}")
    assert r.status_code == 404


def test_workers_listing_empty(client: TestClient) -> None:
    r = client.get("/api/workers")
    assert r.status_code == 200
    assert r.json() == {"workers": []}


def test_test_batch_endpoint_creates_batch_row(client: TestClient) -> None:
    """POST /api/test-batches creates the batch and runs all cases via BackgroundTasks."""
    ver = _commit_flow(client, "tb_flow")

    r = client.put(
        "/api/lookups/tb_cases?profile=default",
        json={
            "fields": ["x"],
            "rows": [{"x": "v1"}, {"x": "v2"}],
        },
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/test-batches",
        json={
            "flow_code": "tb_flow",
            "ver_no": ver,
            "test_ns_code": "tb_cases",
            "profile_code": "default",
            "mock_config": {
                "n1": {"mode": "fixed", "result": {"out": "mock_value"}}
            },
            "concurrency": 2,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    batch_id = body["batch_id"]
    assert body["total_runs"] == 2
    assert body["status"] == "running"

    info = client.get(f"/api/test-batches/{batch_id}").json()
    assert info["id"] == batch_id
    assert info["total_runs"] == 2
    assert info["test_ns_code"] == "tb_cases"
    assert info["status"] == "completed"
    assert info["completed_runs"] + info["error_runs"] == 2
    runs = client.get(f"/api/test-batches/{batch_id}/runs").json()
    assert runs["total"] == 2


def test_test_plan_copy_and_batches_endpoints(client: TestClient) -> None:
    ver = _commit_flow(client, "tp_flow")
    r = client.put(
        "/api/lookups/tp_cases?profile=default",
        # Keep rows empty so /run doesn't spawn background tasks in TestClient.
        json={"fields": ["x"], "rows": []},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/test-plans",
        json={
            "name": "plan1",
            "flow_code": "tp_flow",
            "version_channel": f"v{ver}",
            "test_ns_code": "tp_cases",
            "profile_code": "default",
            "concurrency": 2,
            "mock_config": {"n1": {"mode": "fixed", "result": {"out": "mock_value"}}},
            "context_mapping": {"mode": "wrap", "wrap_key": "alarms", "wrap_as_list": True},
        },
    )
    assert r.status_code == 200, r.text
    plan_id = int(r.json()["id"])

    # Copy plan
    r = client.post(f"/api/test-plans/{plan_id}/copy", json={})
    assert r.status_code == 200, r.text
    copied = r.json()
    assert copied["id"] != plan_id
    assert copied["flow_code"] == "tp_flow"

    # Run original plan twice → should create 2 batches
    r = client.post(f"/api/test-plans/{plan_id}/run", json={})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/test-plans/{plan_id}/run", json={})
    assert r.status_code == 200, r.text

    r = client.get(f"/api/test-plans/{plan_id}/batches?limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan_id"] == plan_id
    assert body["total"] == 2
    assert len(body["batches"]) == 2


def test_recent_failed_deploy_runs_dedup_per_deployment(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    from flow_engine.db.models import FeDeployRun
    from flow_engine.db.session import db_session

    ver = _commit_flow(client, "fail_run_flow")
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "fail_run_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    dep_id = int(r.json()["id"])

    now = datetime.now(timezone.utc)
    with db_session() as s:
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                worker_id="w1",
                flow_code="fail_run_flow",
                ver_no=ver,
                mode="production",
                schedule_type="once",
                trigger_type="manual",
                status="failed",
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4),
                error="older failure",
            )
        )
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                worker_id="w1",
                flow_code="fail_run_flow",
                ver_no=ver,
                mode="production",
                schedule_type="once",
                trigger_type="manual",
                status="failed",
                started_at=now - timedelta(minutes=2),
                finished_at=now - timedelta(minutes=1),
                error="latest failure",
            )
        )

    r = client.get("/api/deploy-runs/recent-failures", params={"hours": 24})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["runs"][0]["deployment_id"] == dep_id
    assert body["runs"][0]["error"] == "latest failure"


def test_recent_overview_deploy_runs_excludes_failed(client: TestClient) -> None:
    from datetime import datetime, timedelta, timezone

    from flow_engine.db.models import FeDeployRun
    from flow_engine.db.session import db_session

    ver = _commit_flow(client, "ov_run_flow")
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "ov_run_flow",
            "ver_no": ver,
            "mode": "production",
            "schedule_type": "once",
            "schedule_config": {},
            "worker_policy": {"type": "single_active", "target_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    dep_id = int(r.json()["id"])

    now = datetime.now(timezone.utc)
    with db_session() as s:
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                worker_id="w1",
                flow_code="ov_run_flow",
                ver_no=ver,
                mode="production",
                schedule_type="once",
                trigger_type="manual",
                status="completed",
                started_at=now - timedelta(minutes=5),
                finished_at=now - timedelta(minutes=4),
            )
        )
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                worker_id="w1",
                flow_code="ov_run_flow",
                ver_no=ver,
                mode="production",
                schedule_type="once",
                trigger_type="manual",
                status="terminated",
                started_at=now - timedelta(minutes=2),
                finished_at=now - timedelta(minutes=1),
            )
        )
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                worker_id="w1",
                flow_code="ov_run_flow",
                ver_no=ver,
                mode="production",
                schedule_type="once",
                trigger_type="manual",
                status="failed",
                started_at=now - timedelta(seconds=30),
                finished_at=now,
                error="should not appear",
            )
        )

    r = client.get("/api/deploy-runs/recent-overview", params={"hours": 24})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["runs"][0]["deployment_id"] == dep_id
    assert body["runs"][0]["status"] == "terminated"


def test_api_rejects_legacy_min_workers(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "schedule_type": "once",
            "worker_policy": {"type": "single_active", "min_workers": 1},
        },
    )
    assert r.status_code == 422
    assert "target_workers" in r.text


def test_api_get_normalizes_legacy_min_workers(client: TestClient) -> None:
    from flow_engine.db.models import FeFlowDeployment
    from flow_engine.db.session import db_session

    ver = _commit_flow(client)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="runner_flow",
            ver_no=ver,
            mode="production",
            schedule_type="once",
            schedule_config={},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            status="stopped",
            env_profile_code="",
            worker_targeting={"mode": "any"},
        )
        s.add(row)
        s.flush()
        dep_id = int(row.id)

    r = client.get(f"/api/deployments/{dep_id}")
    assert r.status_code == 200
    wp = r.json()["worker_policy"]
    assert wp["target_workers"] == 1
    assert "min_workers" not in wp


def test_api_pool_target_workers_must_match(client: TestClient) -> None:
    ver = _commit_flow(client)
    r = client.post(
        "/api/deployments",
        json={
            "flow_code": "runner_flow",
            "ver_no": ver,
            "schedule_type": "cron",
            "schedule_config": {"cron_expr": "0 * * * *"},
            "worker_policy": {"type": "multi_active", "target_workers": 3},
            "worker_targeting": {"mode": "pool", "worker_ids": ["w1", "w2"]},
        },
    )
    assert r.status_code == 400
    assert "target_workers" in r.text

