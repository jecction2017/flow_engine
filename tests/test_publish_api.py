"""Integration tests for versioned flow HTTP API (draft, versions, resolve, run)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Spin up a fresh FastAPI app backed by an isolated flows directory."""
    monkeypatch.setenv("FLOW_ENGINE_FLOWS_DIR", str(tmp_path / "flows"))
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path / "dict"))
    monkeypatch.setenv("FLOW_ENGINE_LOOKUP_DIR", str(tmp_path / "lookup"))
    monkeypatch.setenv("FLOW_ENGINE_PROFILE_DIR", str(tmp_path / "profiles_cfg"))

    import flow_engine.api.http_api as api_mod
    import flow_engine.stores.data_dict as dict_mod
    import flow_engine.stores.profile_store as profile_mod
    import flow_engine.stores.version_store as vs_mod

    dict_mod.invalidate_store_cache()
    profile_mod.invalidate_profile_store_cache()
    importlib.reload(vs_mod)
    importlib.reload(api_mod)

    app = api_mod.create_app()
    return TestClient(app)


def _sample_flow_payload(display_name: str = "demo") -> dict[str, Any]:
    return {
        "display_name": display_name,
        "version": "1.0.0",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [],
    }


def _create_flow(client: TestClient, flow_id: str = "demo") -> None:
    r = client.post("/api/flows", json={"id": flow_id, "display_name": flow_id})
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
    assert r.json()["display_name"] == "foo"


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
    assert r.json()["display_name"] == "inline"


def test_commit_without_draft_or_data_fails(client: TestClient) -> None:
    _create_flow(client, "foo")
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
    r = client.get("/api/flows/foo")
    assert r.status_code == 200 and r.json()["display_name"] == "foo"
    import flow_engine.api.http_api as api_mod

    _commit_version(client, "foo")
    api_mod.registry.version_store("foo").delete_draft()
    r = client.get("/api/flows/foo")
    assert r.status_code == 200


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
    assert body["definition"]["display_name"] == "v2"


def test_resolve_specific_version(client: TestClient) -> None:
    _create_flow(client, "foo")
    _commit_version(client, "foo", name="v1")
    r = client.get("/api/flows/foo/resolve?channel=v1")
    assert r.json()["version"] == 1


def test_resolve_legacy_publish_channel_string_404(client: TestClient) -> None:
    """Production/gray channels are no longer supported."""
    _create_flow(client, "foo")
    _commit_version(client, "foo")
    r = client.get("/api/flows/foo/resolve?channel=production")
    assert r.status_code == 404


def test_resolve_draft(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.put("/api/flows/foo/draft", json=_sample_flow_payload("my-draft"))
    assert r.status_code == 200
    r = client.get("/api/flows/foo/resolve?channel=draft")
    body = r.json()
    assert body["version"] is None
    assert body["definition"]["display_name"] == "my-draft"


# ---------------------------------------------------------------------------
# Flow run + validate
# ---------------------------------------------------------------------------


def test_validate_returns_name_and_version(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/flows/foo/validate")
    assert r.status_code == 200
    assert r.json()["display_name"] == "foo"


def test_run_empty_flow_completes(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/flows/foo/run", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "COMPLETED"
    assert body["ok"] is True
    assert body["resolved_profile"] == "default"
    assert body["resolved_hash"]


def test_run_uses_profile_and_runtime_patch_for_dict_get(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.put("/api/dict/module?layer=base&module_id=app", json={"yaml": "http:\n  timeout_sec: 10\n"})
    assert r.status_code == 200, r.text
    r = client.post("/api/dict/profiles", json={"profile": "dev"})
    assert r.status_code == 200, r.text
    r = client.put(
        "/api/dict/module?layer=profile&profile=dev&module_id=app",
        json={"yaml": "http:\n  timeout_sec: 20\n"},
    )
    assert r.status_code == 200, r.text

    payload = _sample_flow_payload("dict-run")
    payload["nodes"] = [
        {
            "type": "task",
            "id": "read_dict",
            "name": "read_dict",
            "strategy_ref": "default_sync",
            "script": (
                '{"builtin": dict_get("app.http.timeout_sec"), '
                '"snapshot": resolve("$.global.dictionary.app.http.timeout_sec")}\n'
            ),
            "boundary": {
                "inputs": {},
                "outputs": {
                    "builtin": "$.global.builtin",
                    "snapshot": "$.global.snapshot",
                },
            },
        }
    ]
    r = client.put("/api/flows/foo/draft", json=payload)
    assert r.status_code == 200, r.text
    r = client.post(
        "/api/flows/foo/run",
        json={"runtime_patch": {"app": {"http": {"timeout_sec": 30}}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["resolved_profile"] == "dev"
    assert body["global_ns"]["builtin"] == 30
    assert body["global_ns"]["snapshot"] == 30


def test_run_uses_global_default_profile_when_request_omitted(client: TestClient) -> None:
    _create_flow(client, "foo")
    r = client.post("/api/profiles", json={"profile": "dev"})
    assert r.status_code == 200, r.text
    r = client.put("/api/profiles/config", json={"default_profile": "dev"})
    assert r.status_code == 200, r.text

    r = client.put("/api/dict/module?layer=base&module_id=app", json={"yaml": "http:\n  timeout_sec: 10\n"})
    assert r.status_code == 200, r.text
    r = client.put("/api/dict/module?layer=profile&profile=dev&module_id=app", json={"yaml": "http:\n  timeout_sec: 22\n"})
    assert r.status_code == 200, r.text

    payload = _sample_flow_payload("global-default")
    payload["nodes"] = [
        {
            "type": "task",
            "id": "read_dict",
            "name": "read_dict",
            "strategy_ref": "default_sync",
            "script": '{"timeout": dict_get("app.http.timeout_sec")}\n',
            "boundary": {"inputs": {}, "outputs": {"timeout": "$.global.timeout"}},
        }
    ]
    r = client.put("/api/flows/foo/draft", json=payload)
    assert r.status_code == 200, r.text
    r = client.post("/api/flows/foo/run", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolved_profile"] == "dev"
    assert body["global_ns"]["timeout"] == 22


def test_lookup_api_and_runtime_use_selected_profile(client: TestClient) -> None:
    _create_flow(client, "foo")
    client.post("/api/profiles", json={"profile": "dev"})
    client.post("/api/profiles", json={"profile": "sit"})
    client.put("/api/lookups/apps?profile=dev", json={"fields": ["appid"], "rows": [{"appid": "dev-1"}]})
    client.put("/api/lookups/apps?profile=sit", json={"fields": ["appid"], "rows": [{"appid": "sit-1"}]})

    r = client.get("/api/lookups/apps/query?profile=dev&filter={}")
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [{"appid": "dev-1"}]
    r = client.get("/api/lookups/apps/query?profile=sit&filter={}")
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == [{"appid": "sit-1"}]

    payload = _sample_flow_payload("lookup-profile")
    payload["nodes"] = [
        {
            "type": "task",
            "id": "read_lookup",
            "name": "read_lookup",
            "strategy_ref": "default_sync",
            "script": '{"rows": lookup_query("apps", {})}\n',
            "boundary": {"inputs": {}, "outputs": {"rows": "$.global.rows"}},
        }
    ]
    r = client.put("/api/flows/foo/draft", json=payload)
    assert r.status_code == 200, r.text
    r = client.post("/api/flows/foo/run", json={"profile": "sit"})
    assert r.status_code == 200, r.text
    assert r.json()["global_ns"]["rows"] == [{"appid": "sit-1"}]
