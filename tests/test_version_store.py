"""Tests for versioned flow storage: VersionStore / PublishStore / InstanceStore /
FlowVersionRegistry and legacy migration."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from flow_engine.engine.publish_models import (
    ChannelState,
    FlowInstance,
    FlowPublishState,
    PublishStatus,
)
from flow_engine.stores.version_store import (
    FlowVersionRegistry,
    InstanceStore,
    PublishStore,
    VersionStore,
    validate_flow_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_flow(display_name: str = "demo", version: str = "1.0.0") -> dict[str, Any]:
    return {
        "display_name": display_name,
        "version": version,
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [],
    }


# ---------------------------------------------------------------------------
# validate_flow_id
# ---------------------------------------------------------------------------


def test_validate_flow_id_accepts_valid() -> None:
    assert validate_flow_id("demo") == "demo"
    assert validate_flow_id("demo_flow_1") == "demo_flow_1"
    assert validate_flow_id("a-b_c") == "a-b_c"
    assert validate_flow_id("A1") == "A1"


@pytest.mark.parametrize(
    "bad",
    ["", "-leading", "_leading", "bad/slash", "bad.dot", "bad space", "x" * 129],
)
def test_validate_flow_id_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_flow_id(bad)


# ---------------------------------------------------------------------------
# VersionStore: draft
# ---------------------------------------------------------------------------


def test_version_store_save_read_delete_draft(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    assert not vs.has_draft()
    data = _sample_flow()
    vs.save_draft(data)
    assert vs.has_draft()
    assert vs.read_draft() == data

    # Draft flag persisted in meta.json
    meta = vs.read_meta()
    assert meta.has_draft is True
    assert meta.flow_id == "demo"

    vs.delete_draft()
    assert not vs.has_draft()
    assert vs.read_meta().has_draft is False


def test_version_store_read_draft_missing(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "empty")
    with pytest.raises(FileNotFoundError):
        vs.read_draft()


# ---------------------------------------------------------------------------
# VersionStore: versions (immutable)
# ---------------------------------------------------------------------------


def test_version_store_commit_auto_increments(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    v1 = vs.commit_version(_sample_flow("v1-flow"))
    v2 = vs.commit_version(_sample_flow("v2-flow"))
    v3 = vs.commit_version(_sample_flow("v3-flow"))
    assert (v1, v2, v3) == (1, 2, 3)
    assert vs.latest_version_num() == 3

    meta = vs.read_meta()
    assert [v.version for v in meta.versions] == [1, 2, 3]
    assert [v.display_name for v in meta.versions] == ["v1-flow", "v2-flow", "v3-flow"]

    # Each version's data is independently retrievable
    assert vs.read_version(1)["display_name"] == "v1-flow"
    assert vs.read_version(2)["display_name"] == "v2-flow"
    assert vs.read_version(3)["display_name"] == "v3-flow"


def test_version_store_commit_from_draft(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    draft = _sample_flow("draft-flow")
    vs.save_draft(draft)
    v1 = vs.commit_version()  # pulls from draft
    assert v1 == 1
    assert vs.read_version(1) == draft


def test_version_store_commit_without_draft_fails(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    with pytest.raises(FileNotFoundError):
        vs.commit_version()


def test_version_store_read_missing_version(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    with pytest.raises(FileNotFoundError):
        vs.read_version(99)


def test_version_store_commit_description_stored(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    vs.commit_version(_sample_flow(), description="initial release")
    meta = vs.read_meta()
    assert meta.versions[0].description == "initial release"


def test_version_store_delete_removes_tree(tmp_path: Path) -> None:
    vs = VersionStore(tmp_path, "demo")
    vs.save_draft(_sample_flow())
    vs.commit_version()
    assert (tmp_path / "demo").is_dir()
    vs.delete()
    assert not (tmp_path / "demo").exists()


# ---------------------------------------------------------------------------
# PublishStore
# ---------------------------------------------------------------------------


def test_publish_store_default_state(tmp_path: Path) -> None:
    ps = PublishStore(tmp_path, "demo")
    state = ps.read()
    assert state.flow_id == "demo"
    assert state.production.status == PublishStatus.UNPUBLISHED
    assert state.gray.status == PublishStatus.UNPUBLISHED
    assert state.production.version is None


def test_publish_store_atomic_write(tmp_path: Path) -> None:
    ps = PublishStore(tmp_path, "demo")
    state = FlowPublishState(flow_id="demo")
    state.production = ChannelState(version=2, status=PublishStatus.PUBLISHING, published_at=time.time())
    state.gray = ChannelState(version=3, status=PublishStatus.RUNNING, published_at=time.time())
    ps.write(state)

    # No temp files left behind
    tmp_files = list((tmp_path / "demo").glob("*.tmp"))
    assert tmp_files == []

    reloaded = ps.read()
    assert reloaded.production.version == 2
    assert reloaded.production.status == PublishStatus.PUBLISHING
    assert reloaded.gray.version == 3
    assert reloaded.gray.status == PublishStatus.RUNNING


def test_publish_store_reset(tmp_path: Path) -> None:
    ps = PublishStore(tmp_path, "demo")
    state = FlowPublishState(flow_id="demo")
    state.gray = ChannelState(version=1, status=PublishStatus.PUBLISHING)
    ps.write(state)
    ps.reset()
    # After reset, default state returns
    assert ps.read().gray.status == PublishStatus.UNPUBLISHED


# ---------------------------------------------------------------------------
# InstanceStore
# ---------------------------------------------------------------------------


def _make_instance(instance_id: str = "i1", version: int = 1) -> FlowInstance:
    now = time.time()
    return FlowInstance(
        instance_id=instance_id,
        flow_id="demo",
        version=version,
        channel="production",
        started_at=now,
        last_heartbeat=now,
        status="running",
        pid=1234,
        host="localhost",
    )


def test_instance_store_register_list_deregister(tmp_path: Path) -> None:
    s = InstanceStore(tmp_path, "demo")
    assert s.list_instances() == []
    s.register(_make_instance("a"))
    s.register(_make_instance("b"))
    ids = [i.instance_id for i in s.list_instances()]
    assert sorted(ids) == ["a", "b"]

    assert s.deregister("a") is True
    assert s.deregister("a") is False
    assert [i.instance_id for i in s.list_instances()] == ["b"]


def test_instance_store_register_idempotent(tmp_path: Path) -> None:
    s = InstanceStore(tmp_path, "demo")
    inst = _make_instance("a", version=1)
    s.register(inst)
    s.register(inst)  # re-register same id
    assert len(s.list_instances()) == 1


def test_instance_store_heartbeat_updates_timestamp(tmp_path: Path) -> None:
    s = InstanceStore(tmp_path, "demo")
    inst = _make_instance("a")
    inst.last_heartbeat = time.time() - 100
    s.register(inst)
    # Slight delay to ensure heartbeat advances the clock
    time.sleep(0.01)
    updated = s.heartbeat("a")
    assert updated is not None
    assert updated.last_heartbeat > inst.last_heartbeat


def test_instance_store_heartbeat_missing(tmp_path: Path) -> None:
    s = InstanceStore(tmp_path, "demo")
    assert s.heartbeat("nope") is None


def test_instance_store_update_status(tmp_path: Path) -> None:
    s = InstanceStore(tmp_path, "demo")
    s.register(_make_instance("a"))
    inst = s.update_status("a", "failed")
    assert inst is not None and inst.status == "failed"
    assert s.list_instances()[0].status == "failed"


def test_instance_store_stale_filtering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Reload module-level TTL by importing fresh
    import importlib

    monkeypatch.setenv("FLOW_ENGINE_INSTANCE_TTL", "0.05")
    import flow_engine.stores.version_store as vs_mod

    importlib.reload(vs_mod)
    try:
        s = vs_mod.InstanceStore(tmp_path, "demo")
        # Construct a new "current" instance then manually backdate the heartbeat
        inst = FlowInstance(
            instance_id="old",
            flow_id="demo",
            version=1,
            channel="production",
            started_at=time.time() - 10,
            last_heartbeat=time.time() - 10,
            status="running",
        )
        s.register(inst)
        # Stale by default (TTL=0.05s) – should be filtered out
        assert s.list_instances() == []
        # But include_stale=True returns them
        assert len(s.list_instances(include_stale=True)) == 1
    finally:
        # Reset env / reimport so other tests see default TTL
        monkeypatch.delenv("FLOW_ENGINE_INSTANCE_TTL", raising=False)
        importlib.reload(vs_mod)


def test_instance_store_count_running(tmp_path: Path) -> None:
    s = InstanceStore(tmp_path, "demo")
    s.register(_make_instance("a"))
    s.register(_make_instance("b"))
    assert s.count_running() == 2
    s.update_status("a", "stopped")
    assert s.count_running() == 1


def test_instance_store_corrupt_file_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "instances.json").write_text("not valid json", encoding="utf-8")
    s = InstanceStore(tmp_path, "demo")
    assert s.list_instances() == []


# ---------------------------------------------------------------------------
# FlowVersionRegistry
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path: Path) -> FlowVersionRegistry:
    return FlowVersionRegistry(directory=tmp_path)


def test_registry_create_and_list(registry: FlowVersionRegistry) -> None:
    registry.create("foo", _sample_flow("foo"))
    registry.create("bar", _sample_flow("bar"))
    flows = registry.list_flows()
    ids = {f["id"] for f in flows}
    assert ids == {"foo", "bar"}
    for f in flows:
        assert f["has_draft"] is True
        assert f["latest_version"] == 0


def test_registry_exists(registry: FlowVersionRegistry) -> None:
    assert registry.exists("nope") is False
    registry.create("foo", _sample_flow())
    assert registry.exists("foo") is True


def test_registry_delete(registry: FlowVersionRegistry) -> None:
    registry.create("foo", _sample_flow())
    registry.delete("foo")
    assert registry.exists("foo") is False


def test_registry_legacy_migration(tmp_path: Path) -> None:
    # Drop an old flat YAML file
    legacy = tmp_path / "legacy_flow.yaml"
    legacy.write_text(
        yaml.safe_dump(_sample_flow("legacy-flow"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    registry = FlowVersionRegistry(directory=tmp_path)

    # Legacy file is kept for backward compatibility
    assert legacy.is_file()

    # New directory was created with a migrated v1 + draft
    assert (tmp_path / "legacy_flow").is_dir()
    vs = registry.version_store("legacy_flow")
    assert vs.latest_version_num() == 1
    assert vs.has_draft()
    v1 = vs.read_version(1)
    # _migrate_name_field auto-promotes the legacy top-level `name` key to `display_name`.
    assert v1["display_name"] == "legacy-flow"
    assert "name" not in v1

    meta = vs.read_meta()
    assert "legacy" in (meta.versions[0].description or "").lower()


def test_registry_migration_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / "flow_x.yaml"
    legacy.write_text(
        yaml.safe_dump(_sample_flow("flow-x"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    r1 = FlowVersionRegistry(directory=tmp_path)
    assert r1.version_store("flow_x").latest_version_num() == 1

    # Second init should NOT re-migrate (directory already exists)
    r2 = FlowVersionRegistry(directory=tmp_path)
    assert r2.version_store("flow_x").latest_version_num() == 1


def test_registry_list_skips_invalid_id_dirs(tmp_path: Path) -> None:
    # Non-flow directory
    (tmp_path / ".tmp-staging").mkdir()
    (tmp_path / "bad.dot").mkdir()
    (tmp_path / "good_flow").mkdir()
    registry = FlowVersionRegistry(directory=tmp_path)
    ids = {f["id"] for f in registry.list_flows()}
    assert ids == {"good_flow"}


# ---------------------------------------------------------------------------
# FlowVersionRegistry.resolve_version_data
# ---------------------------------------------------------------------------


def test_registry_resolve_latest(registry: FlowVersionRegistry) -> None:
    vs = registry.version_store("foo")
    vs.commit_version(_sample_flow("v1"))
    vs.commit_version(_sample_flow("v2"))
    n, data = registry.resolve_version_data("foo", "latest")
    assert n == 2
    assert data["display_name"] == "v2"


def test_registry_resolve_specific_version(registry: FlowVersionRegistry) -> None:
    vs = registry.version_store("foo")
    vs.commit_version(_sample_flow("v1"))
    vs.commit_version(_sample_flow("v2"))
    n, data = registry.resolve_version_data("foo", "v1")
    assert n == 1 and data["display_name"] == "v1"
    n, data = registry.resolve_version_data("foo", "2")
    assert n == 2 and data["display_name"] == "v2"


def test_registry_resolve_draft(registry: FlowVersionRegistry) -> None:
    vs = registry.version_store("foo")
    vs.save_draft(_sample_flow("draft"))
    n, data = registry.resolve_version_data("foo", "draft")
    assert n is None
    assert data["display_name"] == "draft"


def test_registry_resolve_production_channel(registry: FlowVersionRegistry) -> None:
    vs = registry.version_store("foo")
    vs.commit_version(_sample_flow("v1"))
    vs.commit_version(_sample_flow("v2"))
    ps = registry.publish_store("foo")
    state = ps.read()
    state.production = ChannelState(version=1, status=PublishStatus.RUNNING)
    ps.write(state)
    n, data = registry.resolve_version_data("foo", "production")
    assert n == 1 and data["display_name"] == "v1"


def test_registry_resolve_production_unpublished_raises(registry: FlowVersionRegistry) -> None:
    registry.version_store("foo").commit_version(_sample_flow())
    with pytest.raises(ValueError):
        registry.resolve_version_data("foo", "production")


def test_registry_resolve_latest_no_versions_raises(registry: FlowVersionRegistry) -> None:
    registry.create("foo", _sample_flow())  # only draft
    with pytest.raises(ValueError):
        registry.resolve_version_data("foo", "latest")


def test_registry_resolve_unknown_channel(registry: FlowVersionRegistry) -> None:
    registry.version_store("foo").commit_version(_sample_flow())
    with pytest.raises(ValueError):
        registry.resolve_version_data("foo", "garbage")


def test_registry_resolve_missing_version_number(registry: FlowVersionRegistry) -> None:
    registry.version_store("foo").commit_version(_sample_flow())
    with pytest.raises(FileNotFoundError):
        registry.resolve_version_data("foo", "v99")
