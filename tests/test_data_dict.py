from __future__ import annotations

import pytest

import flow_engine.stores.data_dict as data_dict
from flow_engine.stores.dict_store import DataDictError


def test_resolve_profile_and_runtime_patch(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    st = data_dict.store()
    st.write_module("base", "app", "http:\n  timeout_sec: 10\nfeatures:\n- base\n")
    st.create_profile("dev")
    st.write_module("profile", "app", "http:\n  timeout_sec: 20\nfeatures:\n- dev\n", profile="dev")

    resolved = data_dict.resolve(
        "dev",
        {"app": {"http": {"retries": 2}, "features": ["runtime"]}},
    )

    tree = resolved["resolved_dictionary"]
    assert tree["app"]["http"]["timeout_sec"] == 20
    assert tree["app"]["http"]["retries"] == 2
    assert tree["app"]["features"] == ["runtime"]
    assert resolved["resolved_profile"] == "dev"
    assert isinstance(resolved["resolved_hash"], str) and len(resolved["resolved_hash"]) == 64
    app_module = next(m for m in resolved["resolved_modules"] if m["module_id"] == "app")
    assert app_module["from_base"] is True
    assert app_module["from_profile"] is True


def test_profile_must_exist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    data_dict.store()
    with pytest.raises(DataDictError, match="Profile not found"):
        data_dict.resolve("dev")


def test_lookup_and_dict_get_use_active_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    data_dict.store().write_module("base", "app", "name: base\n")
    from flow_engine.starlark_sdk.python_builtin_impl import dict_get

    assert data_dict.lookup("app.name") == "base"
    with data_dict.dictionary_scope({"app": {"name": "runtime"}}):
        assert data_dict.lookup("app.name") == "runtime"
        assert dict_get("app.name") == "runtime"
    assert dict_get("missing.key", "d") == "d"


def test_invalid_root_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLOW_ENGINE_DICT_DIR", str(tmp_path))
    data_dict.invalidate_store_cache()
    with pytest.raises(DataDictError):
        data_dict.store().write_module("base", "app", "- one\n- two\n")
