"""Integration tests for the version / publish / instance HTTP API."""

from __future__ import annotations

import importlib
import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Spin up a fresh FastAPI app backed by an isolated flows directory.

    We reload the module so the module-level ``registry`` singleton binds to
    the temp dir. Also speed up the publish-timeout watcher so the tests
    don't wait a full minute.
    """
    monkeypatch.setenv("FLOW_ENGINE_FLOWS_DIR", str(tmp_path / "flows"))
    monkeypatch.setenv("FLOW_ENGINE_PUBLISH_TIMEOUT", "0.5")

    # Reload modules that capture env at import time
    import flow_engine.stores.version_store as vs_mod
    import flow_engine.api.http_api as api_mod

    importlib.reload(vs_mod)
    importlib.reload(api_mod)

    # Reset the global event bus so a fresh state machine runs for each test
    from flow_engine.engine import event_bus as bus_mod

    bus_mod.set_event_bus(bus_mod.InMemoryEventBus())

    app = api_mod.create_app()
    return TestClient(app)


def _sample_flow_payload(name: str = "demo") -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0.0",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [],
    }


def _create_flow(client: TestClient, flow_id: str = "demo") -> None:
    r = client.post("/api/flows", json={"id": flow_id, "name": flow_id})
    assert r.status_code == 200, r.text


def _commit_version(client: TestClient, flow_id: str, name: str | None = None) -> int:
    payload = _sample_flow_payload(name or flow_id)
    r = client.put(f"/api/flows/{flow_id}/draft", json=payload)
    assert r.status_code == 200, r.text
    r = client.post(f"/api/flows/{flow_id}/versions", json={})
    assert r.status_code == 200, r.text
    return int(r.json()["version"])


# ---------------------------------------------------------------------------
# Health / listing / create / delete
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_flows_empty(client: TestClient) -> None:
    r = client.get("/api/flows")
    assert r.status_code == 200
    assert r.json()["flows"] == []


def test_create_flow_minimal(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.get("/api/flows")
    ids = [f["id"] for f in r.json()["flows"]]
    assert "foo" in ids


def test_create_flow_conflict(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/flows", json={"id": "foo"})
    assert r.status_code == 409


def test_create_flow_invalid_id(client: TestClient) -> None:
    r = client.post("/api/flows", json={"id": "bad/id"})
    assert r.status_code == 400


def test_delete_flow(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.delete("/api/flows/foo")
    assert r.status_code == 200
    r = client.get("/api/flows")
    assert [f["id"] for f in r.json()["flows"]] == []


def test_delete_flow_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/api/flows/nope")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------


def test_draft_put_and_get(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.get("/api/flows/foo/draft")
    assert r.status_code == 200  # auto-created draft from minimal create
    assert r.json()["name"] == "foo"


def test_draft_put_validates_schema(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.put("/api/flows/foo/draft", json={"garbage": True})
    assert r.status_code == 400


def test_commit_version_increments(client: TestClient) -> None:
    _create_flow(client, "foo")
    v1 = _commit_version(client, "foo")
    v2 = _commit_version(client, "foo")
    v3 = _commit_version(client, "foo")
    assert (v1, v2, v3) == (1, 2, 3)

    r = client.get("/api/flows/foo/versions")
    body = r.json()
    assert body["latest_version"] == 3
    assert [v["version"] for v in body["versions"]] == [1, 2, 3]


def test_commit_with_inline_data(client: TestClient) -> None:
    _create_flow(client, "foo")
    payload = _sample_flow_payload("inline")
    r = client.post("/api/flows/foo/versions", json={"data": payload, "description": "hello"})
    assert r.status_code == 200
    assert r.json()["version"] == 1
    r = client.get("/api/flows/foo/versions/1")
    assert r.status_code == 200
    assert r.json()["name"] == "inline"


def test_commit_without_draft_or_data_fails(client: TestClient) -> None:
    # Create with draft then delete it by writing a version (draft is preserved actually)
    # Simulate a no-draft flow via the filesystem
    _create_flow(client, "foo")
    # Manually remove draft via the store
    import flow_engine.api.http_api as api_mod

    api_mod.registry.version_store("foo").delete_draft()
    r = client.post("/api/flows/foo/versions", json={})
    assert r.status_code == 400


def test_get_missing_version_404(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.get("/api/flows/foo/versions/99")
    assert r.status_code == 404


def test_get_flow_returns_draft_or_latest(client: TestClient) -> None:
    _create_flow(client, "foo")
    # Draft exists – GET /api/flows/foo returns it
    r = client.get("/api/flows/foo")
    assert r.status_code == 200 and r.json()["name"] == "foo"
    # After deleting the draft and committing, returns the latest committed version
    import flow_engine.api.http_api as api_mod

    _commit_version(client, "foo")
    api_mod.registry.version_store("foo").delete_draft()
    r = client.get("/api/flows/foo")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Publish management
# ---------------------------------------------------------------------------


def test_publish_initial_state(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.get("/api/flows/foo/publish")
    body = r.json()
    assert body["production"]["status"] == "unpublished"
    assert body["gray"]["status"] == "unpublished"


def test_publish_to_channel(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    r = client.post("/api/flows/foo/publish", json={"version": 1, "channel": "production"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "publishing"

    state = client.get("/api/flows/foo/publish").json()
    assert state["production"]["status"] == "publishing"
    assert state["production"]["version"] == 1


def test_publish_gray_and_production_independent(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    _commit_version(client, "foo")
    r1 = client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    r2 = client.post("/api/flows/foo/publish", json={"version": 2, "channel": "production"})
    assert r1.status_code == 200 and r2.status_code == 200
    state = client.get("/api/flows/foo/publish").json()
    assert state["gray"]["version"] == 1
    assert state["production"]["version"] == 2


def test_publish_conflict_if_channel_active(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    _commit_version(client, "foo")
    r1 = client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    assert r1.status_code == 200
    r2 = client.post("/api/flows/foo/publish", json={"version": 2, "channel": "gray"})
    assert r2.status_code == 409


def test_publish_missing_version_404(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/flows/foo/publish", json={"version": 99, "channel": "gray"})
    assert r.status_code == 404


def test_publish_invalid_channel_422(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    r = client.post("/api/flows/foo/publish", json={"version": 1, "channel": "canary"})
    # Pydantic pattern validation → 422
    assert r.status_code == 422


def test_stop_publish_resets_channel(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    r = client.delete("/api/flows/foo/publish/gray")
    assert r.status_code == 200

    state = client.get("/api/flows/foo/publish").json()
    assert state["gray"]["status"] == "unpublished"
    assert state["gray"]["stopped_at"] is not None


def test_stop_publish_invalid_channel(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.delete("/api/flows/foo/publish/canary")
    assert r.status_code == 400


def test_publish_then_stop_then_republish(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    _commit_version(client, "foo")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "production"})
    client.delete("/api/flows/foo/publish/production")
    # Now free to publish v2
    r = client.post("/api/flows/foo/publish", json={"version": 2, "channel": "production"})
    assert r.status_code == 200


def test_publish_timeout_auto_fails_when_no_instance(client: TestClient) -> None:
    """PUBLISHING → FAILED after the configured timeout if no instance registers."""
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    r = client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    assert r.status_code == 200
    # Sleep past the 0.5s configured timeout
    time.sleep(1.0)
    state = client.get("/api/flows/foo/publish").json()
    assert state["gray"]["status"] == "failed"


# ---------------------------------------------------------------------------
# resolve channel
# ---------------------------------------------------------------------------


def test_resolve_latest(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo", name="v1")
    _commit_version(client, "foo", name="v2")
    r = client.get("/api/flows/foo/resolve?channel=latest")
    body = r.json()
    assert body["version"] == 2
    assert body["definition"]["name"] == "v2"


def test_resolve_specific_version(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo", name="v1")
    r = client.get("/api/flows/foo/resolve?channel=v1")
    assert r.json()["version"] == 1


def test_resolve_gray(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo", name="v1")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    r = client.get("/api/flows/foo/resolve?channel=gray")
    assert r.json()["version"] == 1


def test_resolve_unpublished_channel_404(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    r = client.get("/api/flows/foo/resolve?channel=production")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Instance management + state-machine transitions
# ---------------------------------------------------------------------------


def _register_instance(
    client: TestClient,
    flow_id: str,
    instance_id: str,
    version: int,
    channel: str = "production",
) -> None:
    r = client.post(
        f"/api/flows/{flow_id}/instances",
        json={
            "instance_id": instance_id,
            "version": version,
            "channel": channel,
            "pid": 1234,
            "host": "localhost",
        },
    )
    assert r.status_code == 200, r.text


def test_register_transitions_publishing_to_running(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})

    _register_instance(client, "foo", "i-1", version=1, channel="gray")
    state = client.get("/api/flows/foo/publish").json()
    assert state["gray"]["status"] == "running"


def test_deregister_all_instances_resets_channel(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    _register_instance(client, "foo", "i-1", version=1, channel="gray")

    r = client.delete("/api/flows/foo/instances/i-1")
    assert r.status_code == 200 and r.json()["found"] is True
    state = client.get("/api/flows/foo/publish").json()
    assert state["gray"]["status"] == "unpublished"


def test_multiple_instances_keep_channel_running(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "production"})

    _register_instance(client, "foo", "i-1", version=1)
    _register_instance(client, "foo", "i-2", version=1)

    # Deregister one – channel still RUNNING because another instance remains
    client.delete("/api/flows/foo/instances/i-1")
    state = client.get("/api/flows/foo/publish").json()
    assert state["production"]["status"] == "running"


def test_heartbeat_updates_instance(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    client.post("/api/flows/foo/publish", json={"version": 1, "channel": "gray"})
    _register_instance(client, "foo", "i-1", version=1, channel="gray")
    r = client.put("/api/flows/foo/instances/i-1", json={"status": "running"})
    assert r.status_code == 200


def test_heartbeat_missing_instance_404(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.put("/api/flows/foo/instances/nope", json={"status": "running"})
    assert r.status_code == 404


def test_list_instances(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    _register_instance(client, "foo", "i-1", version=1)
    _register_instance(client, "foo", "i-2", version=1)
    r = client.get("/api/flows/foo/instances")
    body = r.json()
    ids = sorted(i["instance_id"] for i in body["instances"])
    assert ids == ["i-1", "i-2"]


def test_deregister_unknown_returns_found_false(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.delete("/api/flows/foo/instances/nope")
    assert r.status_code == 200
    assert r.json()["found"] is False


# ---------------------------------------------------------------------------
# Flow run + validate
# ---------------------------------------------------------------------------


def test_validate_returns_name_and_version(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/flows/foo/validate")
    assert r.status_code == 200
    assert r.json()["name"] == "foo"


async def test_run_empty_flow_completes(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/flows/foo/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "COMPLETED"
    assert body["ok"] is True


# ---------------------------------------------------------------------------
# SSE – we exercise the route directly instead of through httpx.ASGITransport,
# because ASGITransport buffers the full response and doesn't support real
# streaming, which makes end-to-end streaming tests deadlock.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# End-to-end lifecycle
# ---------------------------------------------------------------------------


def test_full_lifecycle_e2e(client: TestClient) -> None:
    """Exercises the full lifecycle: create → commit v1 → publish → register →
    deregister → stop → commit v2 → publish v2."""

    _create_flow(client, "lifecycle")
    v1 = _commit_version(client, "lifecycle", name="v1")
    assert v1 == 1

    # Publish v1 to production
    r = client.post("/api/flows/lifecycle/publish", json={"version": v1, "channel": "production"})
    assert r.status_code == 200
    assert client.get("/api/flows/lifecycle/publish").json()["production"]["status"] == "publishing"

    # Register instance – state should flip to running
    _register_instance(client, "lifecycle", "inst-lc-1", version=v1, channel="production")
    assert client.get("/api/flows/lifecycle/publish").json()["production"]["status"] == "running"

    # Resolve production returns v1
    r = client.get("/api/flows/lifecycle/resolve?channel=production")
    assert r.json()["version"] == 1 and r.json()["definition"]["name"] == "v1"

    # Deregister the only instance → channel auto-resets
    client.delete("/api/flows/lifecycle/instances/inst-lc-1")
    assert client.get("/api/flows/lifecycle/publish").json()["production"]["status"] == "unpublished"

    # Commit v2 and publish
    v2 = _commit_version(client, "lifecycle", name="v2")
    assert v2 == 2
    r = client.post("/api/flows/lifecycle/publish", json={"version": v2, "channel": "production"})
    assert r.status_code == 200

    # Register new instance and check resolve
    _register_instance(client, "lifecycle", "inst-lc-2", version=v2, channel="production")
    assert client.get("/api/flows/lifecycle/publish").json()["production"]["version"] == v2
    assert client.get("/api/flows/lifecycle/resolve?channel=production").json()["version"] == v2

    # Clean stop
    client.delete("/api/flows/lifecycle/publish/production")
    assert client.get("/api/flows/lifecycle/publish").json()["production"]["status"] == "unpublished"


async def test_sse_endpoint_exists_and_validates_id(client: TestClient) -> None:
    """An invalid flow id returns 400 at route level – the stream is not opened."""
    r = client.get("/api/flows/bad..id/events")
    assert r.status_code == 400


async def test_sse_initial_snapshot_payload(client: TestClient) -> None:
    """Pull a single chunk from the SSE generator via the ASGI interface."""
    import asyncio

    _create_flow(client, "foo")
    _commit_version(client, "foo")

    app = client.app  # type: ignore[attr-defined]

    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)
        # Terminate the generator once we've received one data chunk
        if message.get("type") == "http.response.body" and b"data:" in message.get(
            "body", b""
        ):
            raise RuntimeError("stop-after-first-chunk")

    async def receive() -> dict:
        # Simulate a client disconnecting after a long wait
        await asyncio.sleep(60)
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/flows/foo/events",
        "raw_path": b"/api/flows/foo/events",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "server": ("test", 80),
        "client": ("test", 1234),
    }

    try:
        await asyncio.wait_for(app(scope, receive, send), timeout=3.0)
    except RuntimeError as e:
        if "stop-after-first-chunk" not in str(e):
            raise

    # Find the body message containing the SSE snapshot
    body_msgs = [m for m in sent if m.get("type") == "http.response.body"]
    assert body_msgs, f"no body messages received; got {sent}"
    body_text = body_msgs[-1]["body"].decode("utf-8")
    assert "data:" in body_text
    payload_line = body_text.split("data:", 1)[1].splitlines()[0].strip()
    payload = json.loads(payload_line)
    assert payload["type"] == "snapshot"
    assert payload["flow_id"] == "foo"
    assert "publish" in payload and "instances" in payload
