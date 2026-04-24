"""Versioned flow storage: directory-per-flow with draft + immutable version snapshots.

Directory layout::

    data/flows/
      {flow_id}/
        meta.json          - FlowMeta index
        draft.yaml         - mutable draft (optional)
        versions/
          v1.yaml          - immutable snapshot
          v2.yaml

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
from flow_engine.engine.version_meta import FlowMeta, FlowVersionMeta

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
        display_name = str(data.get("display_name") or data.get("name") or self.flow_id)
        version_meta = FlowVersionMeta(
            version=new_num,
            created_at=time.time(),
            description=description,
            display_name=display_name,
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
        self._migrate_name_field()

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

    def _migrate_name_field(self) -> None:
        """一次性迁移：流程顶层 ``name`` → ``display_name``；meta.json 里 ``flow_name`` → ``display_name``。

        幂等：文件已经是新格式时跳过。只改**顶层** key，不会误伤节点级 ``name``。
        """
        for flow_dir in self.directory.iterdir():
            if not flow_dir.is_dir():
                continue
            try:
                validate_flow_id(flow_dir.name)
            except ValueError:
                continue
            # 1) draft.yaml + versions/vN.yaml ——顶层 name → display_name
            yaml_paths: list[Path] = []
            draft = flow_dir / "draft.yaml"
            if draft.is_file():
                yaml_paths.append(draft)
            versions_dir = flow_dir / "versions"
            if versions_dir.is_dir():
                yaml_paths.extend(sorted(versions_dir.glob("v*.yaml")))
            for yp in yaml_paths:
                try:
                    data = _read_yaml(yp)
                except (ValueError, OSError, yaml.YAMLError):
                    continue
                if not isinstance(data, dict):
                    continue
                if "name" not in data:
                    continue
                if "display_name" in data:
                    # 已经迁移过；清掉残留的顶层 name 即可。
                    new_data = {k: v for k, v in data.items() if k != "name"}
                else:
                    new_data = {}
                    for k, v in data.items():
                        if k == "name":
                            new_data["display_name"] = v
                        else:
                            new_data[k] = v
                try:
                    _write_yaml(yp, new_data)
                except OSError:
                    continue
            # 2) meta.json：versions[].flow_name → display_name
            meta_path = flow_dir / "meta.json"
            if not meta_path.is_file():
                continue
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            versions = raw.get("versions")
            if not isinstance(versions, list):
                continue
            mutated = False
            for entry in versions:
                if not isinstance(entry, dict):
                    continue
                if "flow_name" in entry:
                    if "display_name" not in entry:
                        entry["display_name"] = entry.get("flow_name", "")
                    entry.pop("flow_name", None)
                    mutated = True
            if mutated:
                try:
                    _atomic_write_json(meta_path, raw)
                except OSError:
                    continue

    def version_store(self, flow_id: str) -> VersionStore:
        return VersionStore(self.directory, flow_id)

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
            display_name = ""
            latest = meta.latest_version
            # 优先从 draft 取 display_name，这样用户改了草稿名还没提交版本时，
            # 下拉/列表也能立即反映新的显示名，避免和编辑器打架。
            if vs.has_draft():
                try:
                    raw = vs.read_draft()
                    display_name = str(raw.get("display_name") or raw.get("name") or "")
                except (FileNotFoundError, ValueError):
                    pass
            if not display_name and latest > 0:
                try:
                    raw = vs.read_version(latest)
                    display_name = str(raw.get("display_name") or raw.get("name") or "")
                except (FileNotFoundError, ValueError):
                    pass
            # UI 约定：空字符串表示没有自定义显示名，前端会 fallback 到 id。
            stat = p.stat()
            out.append(
                {
                    "id": fid,
                    "display_name": display_name,
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
          - "latest"     → latest committed version
          - "draft"      → draft
          - "v3" or "3"  → specific version number
        """
        vs = self.version_store(flow_id)

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
