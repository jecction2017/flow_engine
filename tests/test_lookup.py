from __future__ import annotations

import pytest

from flow_engine.lookup.lookup_import import rows_from_bytes
from flow_engine.lookup.lookup_service import lookup_query, merge_imported_rows, put_table
from flow_engine.lookup.lookup_store import LookupStoreError, invalidate_lookup_store_cache
from flow_engine.stores.profile_store import invalidate_profile_store_cache, profile_scope, store as profile_store


def test_lookup_query_and_import(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_LOOKUP_DIR", str(tmp_path))
    monkeypatch.setenv("FLOW_ENGINE_PROFILE_DIR", str(tmp_path / "profiles_cfg"))
    invalidate_lookup_store_cache()
    invalidate_profile_store_cache()
    profile_store().create_profile("dev")
    with profile_scope("dev"):
        put_table("apps", {"fields": ["appid", "name"], "rows": [{"appid": "1", "name": "a"}]})
        assert lookup_query("apps", {"appid": "1"}) == [{"appid": "1", "name": "a"}]
        assert lookup_query("apps", {"appid": "x"}) == []
        merge_imported_rows("apps", [{"appid": "2", "name": "b"}], mode="append")
        assert len(lookup_query("apps", {})) == 2


def test_lookup_profiles_are_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_LOOKUP_DIR", str(tmp_path))
    monkeypatch.setenv("FLOW_ENGINE_PROFILE_DIR", str(tmp_path / "profiles_cfg"))
    invalidate_lookup_store_cache()
    invalidate_profile_store_cache()
    st = profile_store()
    st.create_profile("dev")
    st.create_profile("sit")
    with profile_scope("dev"):
        put_table("apps", {"rows": [{"appid": "dev-1"}]})
    with profile_scope("sit"):
        put_table("apps", {"rows": [{"appid": "sit-1"}]})
        assert lookup_query("apps", {}) == [{"appid": "sit-1"}]
    with profile_scope("dev"):
        assert lookup_query("apps", {}) == [{"appid": "dev-1"}]


def test_rows_from_csv_json() -> None:
    csv_b = "id,name\n1,ok\n".encode()
    r = rows_from_bytes(csv_b, filename="t.csv", format="csv")
    assert r == [{"id": "1", "name": "ok"}]
    j = b'[{"k":1}]'
    r2 = rows_from_bytes(j, filename="t.json", format="json")
    assert r2 == [{"k": 1}]


def test_invalid_namespace() -> None:
    with pytest.raises(LookupStoreError):
        lookup_query("bad/ns", {})
