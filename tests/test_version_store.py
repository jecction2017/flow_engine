"""Tests for MySQL-backed versioned flow storage: VersionStore, FlowVersionRegistry."""

from __future__ import annotations

from typing import Any

import pytest

from flow_engine.stores.version_store import FlowVersionRegistry, VersionStore, validate_flow_id


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


def test_version_store_save_read_delete_draft() -> None:
    vs = VersionStore("demo")
    assert not vs.has_draft()
    data = _sample_flow()
    vs.save_draft(data)
    assert vs.has_draft()
    assert vs.read_draft() == data

    meta = vs.read_meta()
    assert meta.has_draft is True
    assert meta.flow_id == "demo"

    vs.delete_draft()
    assert not vs.has_draft()
    assert vs.read_meta().has_draft is False


def test_version_store_read_draft_missing() -> None:
    vs = VersionStore("empty")
    with pytest.raises(FileNotFoundError):
        vs.read_draft()


# ---------------------------------------------------------------------------
# VersionStore: versions (immutable)
# ---------------------------------------------------------------------------


def test_version_store_commit_auto_increments() -> None:
    vs = VersionStore("demo")
    v1 = vs.commit_version(_sample_flow("v1-flow"))
    v2 = vs.commit_version(_sample_flow("v2-flow"))
    v3 = vs.commit_version(_sample_flow("v3-flow"))
    assert (v1, v2, v3) == (1, 2, 3)
    assert vs.latest_version_num() == 3

    meta = vs.read_meta()
    assert [v.version for v in meta.versions] == [1, 2, 3]
    assert [v.display_name for v in meta.versions] == ["v1-flow", "v2-flow", "v3-flow"]

    assert vs.read_version(1)["display_name"] == "v1-flow"
    assert vs.read_version(2)["display_name"] == "v2-flow"
    assert vs.read_version(3)["display_name"] == "v3-flow"


def test_version_store_commit_from_draft() -> None:
    vs = VersionStore("demo")
    draft = _sample_flow("draft-flow")
    vs.save_draft(draft)
    v1 = vs.commit_version()  # pulls from draft
    assert v1 == 1
    assert vs.read_version(1) == draft


def test_version_store_commit_without_draft_fails() -> None:
    vs = VersionStore("demo")
    with pytest.raises(FileNotFoundError):
        vs.commit_version()


def test_version_store_read_missing_version() -> None:
    vs = VersionStore("demo")
    with pytest.raises(FileNotFoundError):
        vs.read_version(99)


def test_version_store_commit_description_stored() -> None:
    vs = VersionStore("demo")
    vs.commit_version(_sample_flow(), description="initial release")
    meta = vs.read_meta()
    assert meta.versions[0].description == "initial release"


def test_version_store_delete_soft_removes_flow() -> None:
    vs = VersionStore("demo")
    vs.save_draft(_sample_flow())
    vs.commit_version()
    registry = FlowVersionRegistry()
    assert registry.exists("demo")
    vs.delete()
    assert not registry.exists("demo")


# ---------------------------------------------------------------------------
# FlowVersionRegistry
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> FlowVersionRegistry:
    return FlowVersionRegistry()


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


def test_registry_list_returns_empty_for_new_db(registry: FlowVersionRegistry) -> None:
    assert registry.list_flows() == []


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
