"""Tests for MySQL-backed DataDictStore and data_dict resolution."""

from __future__ import annotations

import pytest

import flow_engine.stores.data_dict as data_dict
from flow_engine.stores.dict_store import DataDictError
from flow_engine.stores.profile_store import store as profile_store


def test_resolve_profile_and_runtime_patch() -> None:
    # Create "dev" profile in fe_env_profile first
    profile_store().create_profile("dev")

    st = data_dict.store()
    st.write_module("base", "app", "http:\n  timeout_sec: 10\nfeatures:\n- base\n")
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


def test_profile_must_exist() -> None:
    # "nonexistent" was never created in fe_env_profile
    with pytest.raises(DataDictError, match="Profile not found"):
        data_dict.resolve("nonexistent")


def test_lookup_and_dict_get_use_active_scope() -> None:
    st = data_dict.store()
    st.write_module("base", "app", "name: base\n")
    from flow_engine.starlark_sdk.python_builtin_impl import dict_get

    assert data_dict.lookup("app.name") == "base"
    with data_dict.dictionary_scope({"app": {"name": "runtime"}}):
        assert data_dict.lookup("app.name") == "runtime"
        assert dict_get("app.name") == "runtime"
    assert dict_get("missing.key", "d") == "d"


def test_invalid_root_raises() -> None:
    with pytest.raises(DataDictError):
        data_dict.store().write_module("base", "app", "- one\n- two\n")


def test_default_profile_exists_automatically() -> None:
    """The 'default' profile is auto-created by GlobalProfileStore.__init__."""
    profiles = profile_store().list_profiles()
    assert "default" in profiles


def test_base_core_module_exists_automatically() -> None:
    modules = [m.module_id for m in data_dict.store().list_modules("base")]
    assert "core" in modules


def test_write_and_read_module_roundtrip() -> None:
    st = data_dict.store()
    content = "key: value\nnested:\n  a: 1\n"
    st.write_module("base", "mymod", content)
    raw = st.read_module_raw("base", "mymod")
    assert "key" in raw
    parsed = st.read_module("base", "mymod")
    assert parsed["key"] == "value"
    assert parsed["nested"]["a"] == 1


def test_delete_module() -> None:
    st = data_dict.store()
    st.write_module("base", "mymod", "x: 1\n")
    st.delete_module("base", "mymod")
    with pytest.raises(DataDictError):
        st.read_module_raw("base", "mymod")


def test_cannot_delete_core_base_module() -> None:
    with pytest.raises(DataDictError, match="core base module cannot be deleted"):
        data_dict.store().delete_module("base", "core")
