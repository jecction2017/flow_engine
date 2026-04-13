from __future__ import annotations

import pytest

from flow_engine.lookup_import import rows_from_bytes
from flow_engine.lookup_service import lookup_query, merge_imported_rows, put_table
from flow_engine.lookup_store import LookupStoreError, invalidate_lookup_store_cache


def test_lookup_query_and_import(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_LOOKUP_DIR", str(tmp_path))
    invalidate_lookup_store_cache()
    put_table("apps", {"fields": ["appid", "name"], "rows": [{"appid": "1", "name": "a"}]})
    assert lookup_query("apps", {"appid": "1"}) == [{"appid": "1", "name": "a"}]
    assert lookup_query("apps", {"appid": "x"}) == []
    merge_imported_rows("apps", [{"appid": "2", "name": "b"}], mode="append")
    assert len(lookup_query("apps", {})) == 2


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
