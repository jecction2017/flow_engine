from __future__ import annotations

import pytest

import flow_engine.stores.data_dict as data_dict
from flow_engine.stores.dict_store import DataDictError, get_at_path


def test_lookup_and_dict_get(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    data_dict.store().write_raw("app:\n  http:\n    timeout_sec: 15\n")
    assert data_dict.lookup("app.http.timeout_sec") == 15
    assert data_dict.lookup("missing.key", "d") == "d"
    from flow_engine.starlark_sdk.python_builtin_impl import dict_get

    assert dict_get("app.http.timeout_sec") == 15


def test_subtree_apply_and_delete(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    data_dict.store().write_raw("a: 1\n")
    data_dict.apply_subtree_yaml("b", "c: 2\n")
    tree = data_dict.store().read_tree()
    assert get_at_path(tree, ["b", "c"]) == 2
    data_dict.delete_path("b")
    tree = data_dict.store().read_tree()
    assert "b" not in tree
    assert tree.get("a") == 1


def test_invalid_root_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    with pytest.raises(DataDictError):
        data_dict.store().write_raw("- one\n- two\n")
