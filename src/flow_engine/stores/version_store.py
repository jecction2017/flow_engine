"""Versioned flow storage: directory-per-flow with draft + immutable version snapshots.

Directory layout::

    data/flows/
      {flow_id}/
        meta.json          - FlowMeta index
        draft.yaml         - mutable draft (optional)
        versions/
          v1.yaml          - immutable snapshot
          v2.yaml
        publish.json       - FlowPublishState
        instances.json     - list[FlowInstance]

Migration: legacy flat ``{flow_id}.yaml`` files are automatically promoted to
``{flow_id}/versions/v1.yaml`` on first access.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from flow_engine._repo_root import repo_root
from flow_engine.engine.publish_models import (
    ChannelState,
    FlowInstance,
    FlowMeta,
    FlowPublishState,
    FlowVersionMeta,
    PublishStatus,
)

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")


def _flows_dir() -> Path:
    raw = os.environ.get("FLOW_ENGINE_FLOWS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root() / "data" / "flows").resolve()


def validate_flow_id(flow_id: str) -> str:
    if not flow_id or not _SAFE_ID.match(flow_id):
        raise ValueError(
            "Invalid flow id: use letters, digits, underscore or hyphen (max 128 chars).",
        )
    return flow_id


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


# ---------------------------------------------------------------------------
# VersionStore
# ---------------------------------------------------------------------------


class VersionStore:
    """Manages versioned flow YAML snapshots + draft for a single flow_id."""

    def __init__(self, base_dir: Path, flow_id: str) -> None:
        validate_flow_id(flow_id)
        self.flow_id = flow_id
        self.root = base_dir / flow_id
        self.versions_dir = self.root / "versions"
        self._meta_path = self.root / "meta.json"
        self._draft_path = self.root / "draft.yaml"

    def _ensure_dirs(self) -> None:
        self.versions_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def read_meta(self) -> FlowMeta:
        if self._meta_path.is_file():
            raw = json.loads(self._meta_path.read_text(encoding="utf-8"))
            return FlowMeta.model_validate(raw)
        return FlowMeta(flow_id=self.flow_id)

    def _write_meta(self, meta: FlowMeta) -> None:
        _atomic_write_json(self._meta_path, meta.model_dump())

    # ------------------------------------------------------------------
    # Draft
    # ------------------------------------------------------------------

    def has_draft(self) -> bool:
        return self._draft_path.is_file()

    def read_draft(self) -> dict[str, Any]:
        if not self._draft_path.is_file():
            raise FileNotFoundError(f"No draft for flow '{self.flow_id}'")
        return _read_yaml(self._draft_path)

    def save_draft(self, data: dict[str, Any]) -> None:
        self._ensure_dirs()
        _write_yaml(self._draft_path, data)
        meta = self.read_meta()
        meta.has_draft = True
        self._write_meta(meta)

    def delete_draft(self) -> None:
        if self._draft_path.is_file():
            self._draft_path.unlink()
        meta = self.read_meta()
        meta.has_draft = False
        self._write_meta(meta)

    # ------------------------------------------------------------------
    # Versions (immutable snapshots)
    # ------------------------------------------------------------------

    def list_versions(self) -> list[FlowVersionMeta]:
        return self.read_meta().versions

    def read_version(self, version: int) -> dict[str, Any]:
        path = self.versions_dir / f"v{version}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Version v{version} not found for flow '{self.flow_id}'")
        return _read_yaml(path)

    def commit_version(self, data: dict[str, Any] | None = None, description: str | None = None) -> int:
        """Commit draft (or supplied data) as a new immutable version. Returns new version number."""
        self._ensure_dirs()
        if data is None:
            data = self.read_draft()
        meta = self.read_meta()
        new_num = meta.latest_version + 1
        path = self.versions_dir / f"v{new_num}.yaml"
        _write_yaml(path, data)
        flow_name = str(data.get("name", self.flow_id))
        version_meta = FlowVersionMeta(
            version=new_num,
            created_at=time.time(),
            description=description,
            flow_name=flow_name,
        )
        meta.versions.append(version_meta)
        meta.latest_version = new_num
        self._write_meta(meta)
        return new_num

    def latest_version_num(self) -> int:
        return self.read_meta().latest_version

    def delete(self) -> None:
        """Remove entire flow directory."""
        if self.root.is_dir():
            shutil.rmtree(self.root)


# ---------------------------------------------------------------------------
# PublishStore
# ---------------------------------------------------------------------------


class PublishStore:
    """Reads/writes the ``publish.json`` file for a flow."""

    def __init__(self, base_dir: Path, flow_id: str) -> None:
        self.flow_id = flow_id
        self._path = base_dir / flow_id / "publish.json"

    def read(self) -> FlowPublishState:
        if not self._path.is_file():
            return FlowPublishState(flow_id=self.flow_id)
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return FlowPublishState.model_validate(raw)

    def write(self, state: FlowPublishState) -> None:
        _atomic_write_json(self._path, state.model_dump())

    def reset(self) -> None:
        if self._path.is_file():
            self._path.unlink()


# ---------------------------------------------------------------------------
# InstanceStore
# ---------------------------------------------------------------------------

_HEARTBEAT_TTL = float(os.environ.get("FLOW_ENGINE_INSTANCE_TTL", "120"))


class InstanceStore:
    """Reads/writes the ``instances.json`` registry for a flow."""

    def __init__(self, base_dir: Path, flow_id: str) -> None:
        self.flow_id = flow_id
        self._path = base_dir / flow_id / "instances.json"

    def _load_raw(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_raw(self, items: list[dict[str, Any]]) -> None:
        _atomic_write_json(self._path, items)

    def list_instances(self, include_stale: bool = False) -> list[FlowInstance]:
        now = time.time()
        out: list[FlowInstance] = []
        for raw in self._load_raw():
            inst = FlowInstance.model_validate(raw)
            if not include_stale and now - inst.last_heartbeat > _HEARTBEAT_TTL:
                continue
            out.append(inst)
        return out

    def register(self, instance: FlowInstance) -> None:
        items = self._load_raw()
        items = [i for i in items if i.get("instance_id") != instance.instance_id]
        items.append(instance.model_dump())
        self._save_raw(items)

    def heartbeat(self, instance_id: str) -> FlowInstance | None:
        items = self._load_raw()
        found: FlowInstance | None = None
        for item in items:
            if item.get("instance_id") == instance_id:
                item["last_heartbeat"] = time.time()
                found = FlowInstance.model_validate(item)
                break
        if found:
            self._save_raw(items)
        return found

    def update_status(self, instance_id: str, status: str) -> FlowInstance | None:
        items = self._load_raw()
        found: FlowInstance | None = None
        for item in items:
            if item.get("instance_id") == instance_id:
                item["status"] = status
                item["last_heartbeat"] = time.time()
                found = FlowInstance.model_validate(item)
                break
        if found:
            self._save_raw(items)
        return found

    def deregister(self, instance_id: str) -> bool:
        items = self._load_raw()
        new_items = [i for i in items if i.get("instance_id") != instance_id]
        if len(new_items) < len(items):
            self._save_raw(new_items)
            return True
        return False

    def count_running(self) -> int:
        return sum(1 for i in self.list_instances() if i.status == "running")


# ---------------------------------------------------------------------------
# FlowVersionRegistry  (top-level: manages all flows)
# ---------------------------------------------------------------------------


class FlowVersionRegistry:
    """Top-level registry that manages versioned flows in a base directory.

    Also handles migration from legacy flat ``{flow_id}.yaml`` files.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _flows_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        """Promote old-style ``{id}.yaml`` files to v1 snapshots.

        The original flat YAML files are intentionally kept so that any code
        that references them by path directly (e.g. tests using
        ``load_flow_from_yaml``) continues to work unchanged.
        """
        for p in list(self.directory.glob("*.yaml")):
            fid = p.stem
            try:
                validate_flow_id(fid)
            except ValueError:
                continue
            target_dir = self.directory / fid
            if target_dir.is_dir():
                # Already migrated – leave original file in place
                continue
            try:
                data = _read_yaml(p)
            except Exception:
                continue
            vs = self.version_store(fid)
            vs.commit_version(data, description="Migrated from legacy flat file")
            vs.save_draft(data)
            # Original file stays – backward compatible

    def version_store(self, flow_id: str) -> VersionStore:
        return VersionStore(self.directory, flow_id)

    def publish_store(self, flow_id: str) -> PublishStore:
        return PublishStore(self.directory, flow_id)

    def instance_store(self, flow_id: str) -> InstanceStore:
        return InstanceStore(self.directory, flow_id)

    def list_flows(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.directory.is_dir():
            return out
        for p in sorted(self.directory.iterdir()):
            if not p.is_dir():
                continue
            fid = p.name
            try:
                validate_flow_id(fid)
            except ValueError:
                continue
            vs = VersionStore(self.directory, fid)
            meta = vs.read_meta()
            name = fid
            latest = meta.latest_version
            if latest > 0:
                try:
                    raw = vs.read_version(latest)
                    name = str(raw.get("name", fid))
                except (FileNotFoundError, ValueError):
                    pass
            elif vs.has_draft():
                try:
                    raw = vs.read_draft()
                    name = str(raw.get("name", fid))
                except (FileNotFoundError, ValueError):
                    pass
            stat = p.stat()
            out.append(
                {
                    "id": fid,
                    "name": name,
                    "path": str(p),
                    "updated_at": stat.st_mtime,
                    "latest_version": latest,
                    "has_draft": meta.has_draft,
                }
            )
        return out

    def exists(self, flow_id: str) -> bool:
        try:
            validate_flow_id(flow_id)
        except ValueError:
            return False
        return (self.directory / flow_id).is_dir()

    def create(self, flow_id: str, initial_data: dict[str, Any]) -> None:
        validate_flow_id(flow_id)
        vs = self.version_store(flow_id)
        vs.save_draft(initial_data)

    def delete(self, flow_id: str) -> None:
        validate_flow_id(flow_id)
        vs = self.version_store(flow_id)
        vs.delete()

    def resolve_version_data(self, flow_id: str, channel: str) -> tuple[int | None, dict[str, Any]]:
        """Resolve a channel/version string to (version_num, flow_data).

        channel values:
          - "production" | "gray"  → look up publish state
          - "latest"               → latest committed version
          - "draft"                → draft
          - "v3" or "3"           → specific version number
        """
        vs = self.version_store(flow_id)
        ps = self.publish_store(flow_id)

        if channel in ("production", "gray"):
            state = ps.read()
            ch = state.production if channel == "production" else state.gray
            if ch.version is None:
                raise ValueError(f"Channel '{channel}' is not published for flow '{flow_id}'")
            return ch.version, vs.read_version(ch.version)

        if channel == "latest":
            meta = vs.read_meta()
            if meta.latest_version == 0:
                raise ValueError(f"No versions committed for flow '{flow_id}'")
            return meta.latest_version, vs.read_version(meta.latest_version)

        if channel == "draft":
            return None, vs.read_draft()

        # parse "v3" or "3"
        raw = channel.lstrip("vV")
        try:
            n = int(raw)
        except ValueError:
            raise ValueError(f"Unknown channel/version: '{channel}'")
        return n, vs.read_version(n)
