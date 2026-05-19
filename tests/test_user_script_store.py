import uuid

from flow_engine.starlark_sdk.user_script_store import (
    MODULE_PLACEHOLDER_REL,
    UserScriptStore,
    is_module_placeholder_rel,
)


def test_put_script_persists_description_and_export_functions() -> None:
    store = UserScriptStore()
    tenant = "test_tenant"
    rel = f"demo/sample_{uuid.uuid4().hex[:8]}.star"
    if store.exists(tenant, rel):
        store.delete_script(tenant, rel)

    content = 'def hello():\n    return {"ok": True}\n'
    store.put_script(tenant, rel, content, description="示例脚本")
    record = store.get_script_record(tenant, rel)
    assert record["description"] == "示例脚本"
    assert record["export_functions"] == ["hello"]
    assert record["content"] == content

    assert store.delete_script(tenant, rel) is True
    assert store.delete_script(tenant, rel) is False


def test_delete_module_soft_deletes_all_scripts() -> None:
    store = UserScriptStore()
    tenant = f"mod_{uuid.uuid4().hex[:8]}"
    rel_a = f"demo/a_{uuid.uuid4().hex[:6]}.star"
    rel_b = f"demo/b_{uuid.uuid4().hex[:6]}.star"
    for rel in (rel_a, rel_b):
        if store.exists(tenant, rel):
            store.delete_script(tenant, rel)
        store.put_script(tenant, rel, '{"ok": True}\n')

    assert store.delete_module(tenant) == 2
    assert not store.exists(tenant, rel_a)
    assert store.delete_module(tenant) == 0


def test_put_script_accepts_explicit_export_functions() -> None:
    store = UserScriptStore()
    tenant = f"exp_{uuid.uuid4().hex[:8]}"
    rel = f"demo/manual_{uuid.uuid4().hex[:6]}.star"
    if store.exists(tenant, rel):
        store.delete_script(tenant, rel)

    store.put_script(
        tenant,
        rel,
        'def ignored():\n    return 1\n',
        export_functions=["alpha", "beta"],
    )
    record = store.get_script_record(tenant, rel)
    assert record["export_functions"] == ["alpha", "beta"]

    assert store.delete_script(tenant, rel) is True


def test_ensure_module_creates_placeholder_and_survives_list() -> None:
    store = UserScriptStore()
    tenant = f"mod_{uuid.uuid4().hex[:8]}"
    store.delete_module(tenant)

    assert store.ensure_module(tenant) is True
    assert store.exists(tenant, MODULE_PLACEHOLDER_REL)
    assert is_module_placeholder_rel(MODULE_PLACEHOLDER_REL)
    paths = store.list_rel_paths()
    assert f"{tenant}/{MODULE_PLACEHOLDER_REL}" not in paths
    listed = store.list_scripts()
    assert any(r["tenant"] == tenant and r["rel_path"] == MODULE_PLACEHOLDER_REL for r in listed)

    assert store.ensure_module(tenant) is False

    rel = f"demo/real_{uuid.uuid4().hex[:6]}.star"
    store.put_script(tenant, rel, '{"ok": True}\n')
    assert not store.exists(tenant, MODULE_PLACEHOLDER_REL)
    assert store.exists(tenant, rel)

    assert store.delete_module(tenant) >= 1
    assert not store.exists(tenant, rel)
