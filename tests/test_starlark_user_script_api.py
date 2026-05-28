"""HTTP tests for user script save-time syntax validation."""

from __future__ import annotations

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


def test_put_user_script_rejects_invalid_starlark_and_does_not_persist(client: TestClient) -> None:
    tenant = "demo"
    rel_path = "syntax/bad.star"
    invalid_script = "def broken(\n    return 1\n"

    put = client.put(
        f"/api/starlark/user/{tenant}/{rel_path}",
        json={"content": invalid_script, "description": "bad"},
    )
    assert put.status_code == 400
    detail = str(put.json().get("detail", ""))
    assert "Starlark 语法错误" in detail
    assert f"user://{tenant}/{rel_path}" in detail

    get = client.get(f"/api/starlark/user/{tenant}/{rel_path}")
    assert get.status_code == 404


def test_put_user_script_accepts_valid_starlark(client: TestClient) -> None:
    tenant = "demo"
    rel_path = "syntax/good.star"
    valid_script = 'def ok():\n    return {"ok": True}\n'

    put = client.put(
        f"/api/starlark/user/{tenant}/{rel_path}",
        json={"content": valid_script, "description": "good"},
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["path"] == f"{tenant}/{rel_path}"
    assert body["content"] == valid_script
    assert body["export_functions"] == ["ok"]
