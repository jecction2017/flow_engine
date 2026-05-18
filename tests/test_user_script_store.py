import uuid

from flow_engine.starlark_sdk.user_script_store import UserScriptStore


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

    store.delete_script(tenant, rel)
