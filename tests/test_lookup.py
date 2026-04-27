"""Tests for MySQL-backed LookupStore and lookup service."""

from __future__ import annotations

import pytest

from flow_engine.lookup.lookup_import import rows_from_bytes
from flow_engine.lookup.lookup_service import lookup_query, merge_imported_rows, put_table
from flow_engine.lookup.lookup_store import LookupStoreError, get_lookup_store
from flow_engine.stores.profile_store import profile_scope, store as profile_store


def test_lookup_query_and_import() -> None:
    profile_store().create_profile("dev")
    with profile_scope("dev"):
        put_table("apps", {"fields": ["appid", "name"], "rows": [{"appid": "1", "name": "a"}]})
        assert lookup_query("apps", {"appid": "1"}) == [{"appid": "1", "name": "a"}]
        assert lookup_query("apps", {"appid": "x"}) == []
        merge_imported_rows("apps", [{"appid": "2", "name": "b"}], mode="append")
        assert len(lookup_query("apps", {})) == 2


def test_lookup_profiles_are_isolated() -> None:
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


def test_list_namespaces_empty() -> None:
    assert get_lookup_store().list_namespaces(profile="default") == []


def test_write_and_read_table_roundtrip() -> None:
    table = {
        "schema": {"type": "object", "properties": {"id": {"type": "string"}}},
        "rows": [{"id": "a"}, {"id": "b"}],
    }
    get_lookup_store().write_table("myns", table)
    result = get_lookup_store().read_table("myns")
    assert len(result["rows"]) == 2
    assert result["rows"][0]["id"] == "a"


def test_replace_table_clears_old_rows() -> None:
    st = get_lookup_store()
    st.write_table("myns", {"rows": [{"id": "old"}]})
    st.write_table("myns", {"rows": [{"id": "new1"}, {"id": "new2"}]})
    rows = st.read_table("myns")["rows"]
    assert len(rows) == 2
    assert rows[0]["id"] == "new1"


def test_delete_namespace() -> None:
    st = get_lookup_store()
    st.write_table("myns", {"rows": [{"id": "1"}]})
    assert st.exists("myns")
    st.delete_namespace("myns")
    assert not st.exists("myns")
    result = st.read_table("myns")
    assert result["rows"] == []
