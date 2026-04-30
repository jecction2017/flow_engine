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
            "worker_policy": {"type": "single_active", "min_workers": 1},
            "capability_policy": [],
            "env_profile_code": "default",
        },
    )
    assert r.status_code == 200, r.text
    dep = r.json()
    assert dep["status"] == "pending"
    assert dep["schedule_type"] == "once"

    r = client.get("/api/deployments")
    assert r.status_code == 200
    rows = r.json()["deployments"]
    assert any(d["id"] == dep["id"] for d in rows)


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
    """POST /api/test-batches creates the batch row synchronously and returns batch_id.

    Note: the per-row run loop is dispatched as an asyncio Task that keeps
    running on the request's event loop; TestClient tears that loop down on
    response so only the batch creation step is observable here. The test
    runner's end-to-end behaviour is covered separately in
    ``test_runner_persistence.test_test_runner_creates_batch_and_runs``.
    """
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
