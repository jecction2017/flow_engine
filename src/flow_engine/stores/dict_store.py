"""YAML-backed modular data dictionary storage."""

from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from flow_engine._repo_root import repo_root
from flow_engine.engine.exceptions import FlowEngineError


class DataDictError(FlowEngineError):
    """Invalid dictionary file, id, or path."""


CORE_MODULE_ID = "core"
DEFAULT_PROFILE_ID = "default"
MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
PROFILE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
DictLayer = Literal["base", "profile"]


@dataclass(frozen=True)
class DictModule:
    module_id: str
    layer: DictLayer
    path: str
    profile: str | None = None


def _dict_dir() -> Path:
    raw = os.environ.get("FLOW_ENGINE_DICT_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root() / "data" / "dict").resolve()


def validate_module_id(module_id: str) -> str:
    mid = (module_id or "").strip()
    if not MODULE_ID_PATTERN.fullmatch(mid):
        raise DataDictError(
            f"Invalid module_id {module_id!r}; expected ^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$"
        )
    return mid


def validate_profile_id(profile_id: str) -> str:
    pid = (profile_id or "").strip()
    if not PROFILE_ID_PATTERN.fullmatch(pid):
        raise DataDictError(
            f"Invalid profile_id {profile_id!r}; expected ^[a-z][a-z0-9_-]{{0,63}}$"
        )
    return pid


def module_id_to_path(module_id: str) -> Path:
    mid = validate_module_id(module_id)
    parts = mid.split(".")
    return Path(*parts[:-1], f"{parts[-1]}.yaml")


def path_to_module_id(path: Path) -> str:
    if path.suffix.lower() not in {".yaml", ".yml"}:
        raise DataDictError(f"Dictionary module must be a YAML file: {path}")
    parts = list(path.with_suffix("").parts)
    return validate_module_id(".".join(parts))


def _parse_yaml_mapping(text: str, *, label: str) -> dict[str, Any]:
    if not text.strip():
        data: Any = {}
    else:
        data = yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise DataDictError(f"{label} root must be a mapping (object)")
    return data


def _dump_yaml_mapping(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        raise DataDictError("dictionary module root must be a mapping (object)")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


class DataDictStore:
    """Layered module store rooted at ``data/dict``.

    Layout:
      - ``base/<module_path>.yaml``
      - ``profiles/<profile_id>/<module_path>.yaml``
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _dict_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir(DEFAULT_PROFILE_ID, create=True)
        core_path = self.module_path("base", CORE_MODULE_ID)
        if not core_path.exists():
            self.write_module("base", CORE_MODULE_ID, "{}\n")

    @property
    def base_dir(self) -> Path:
        return self.directory / "base"

    @property
    def profiles_dir(self) -> Path:
        return self.directory / "profiles"

    def profile_dir(self, profile_id: str, *, create: bool = False) -> Path:
        pid = validate_profile_id(profile_id)
        p = self.profiles_dir / pid
        if create:
            p.mkdir(parents=True, exist_ok=True)
        return p

    def ensure_profile(self, profile_id: str) -> Path:
        p = self.profile_dir(profile_id)
        if not p.is_dir():
            raise DataDictError(f"Profile not found: {profile_id}")
        return p

    def create_profile(self, profile_id: str) -> None:
        self.profile_dir(profile_id, create=True)

    def list_profiles(self) -> list[str]:
        if not self.profiles_dir.is_dir():
            return []
        return sorted(
            validate_profile_id(p.name)
            for p in self.profiles_dir.iterdir()
            if p.is_dir() and PROFILE_ID_PATTERN.fullmatch(p.name)
        )

    def module_path(self, layer: DictLayer, module_id: str, *, profile: str | None = None) -> Path:
        rel = module_id_to_path(module_id)
        if layer == "base":
            return self.base_dir / rel
        if layer == "profile":
            if profile is None:
                raise DataDictError("profile is required for profile modules")
            return self.profile_dir(profile) / rel
        raise DataDictError(f"Invalid dictionary layer: {layer!r}")

    def _iter_module_files(self, root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        files = [p for p in root.rglob("*.yaml") if p.is_file()]
        files.extend(p for p in root.rglob("*.yml") if p.is_file())
        return sorted(files, key=lambda p: p.relative_to(root).as_posix())

    def list_modules(self, layer: DictLayer, *, profile: str | None = None) -> list[DictModule]:
        root = self.base_dir if layer == "base" else self.ensure_profile(profile or "")
        out: list[DictModule] = []
        for p in self._iter_module_files(root):
            rel = p.relative_to(root)
            module_id = path_to_module_id(rel)
            out.append(
                DictModule(
                    module_id=module_id,
                    layer=layer,
                    profile=profile if layer == "profile" else None,
                    path=str(p),
                )
            )
        return out

    def read_module_raw(self, layer: DictLayer, module_id: str, *, profile: str | None = None) -> str:
        p = self.module_path(layer, module_id, profile=profile)
        if not p.is_file():
            raise DataDictError(f"Dictionary module not found: {module_id}")
        return p.read_text(encoding="utf-8")

    def read_module(self, layer: DictLayer, module_id: str, *, profile: str | None = None) -> dict[str, Any]:
        raw = self.read_module_raw(layer, module_id, profile=profile)
        return copy.deepcopy(_parse_yaml_mapping(raw, label=f"{layer} module {module_id}"))

    def write_module(self, layer: DictLayer, module_id: str, text: str, *, profile: str | None = None) -> None:
        data = _parse_yaml_mapping(text, label=f"{layer} module {module_id}")
        p = self.module_path(layer, module_id, profile=profile)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_dump_yaml_mapping(data), encoding="utf-8", newline="\n")

    def delete_module(self, layer: DictLayer, module_id: str, *, profile: str | None = None) -> None:
        mid = validate_module_id(module_id)
        if layer == "base" and mid == CORE_MODULE_ID:
            raise DataDictError("core base module cannot be deleted")
        p = self.module_path(layer, mid, profile=profile)
        if p.exists():
            p.unlink()
        # Clean empty parent directories without crossing the layer root.
        root = self.base_dir if layer == "base" else self.profile_dir(profile or "")
        cur = p.parent
        while cur != root and cur.exists() and not any(cur.iterdir()):
            cur.rmdir()
            cur = cur.parent


def parse_path(path: str) -> list[str]:
    p = path.strip().strip(".")
    if not p:
        return []
    parts: list[str] = []
    for seg in p.split("."):
        s = seg.strip()
        if not s:
            raise DataDictError(f"Invalid dictionary path: {path!r}")
        parts.append(s)
    return parts


def get_at_path(tree: dict[str, Any], parts: list[str]) -> Any:
    if not parts:
        return tree
    cur: Any = tree
    for key in parts:
        if not isinstance(cur, dict):
            raise DataDictError(f"Not a mapping at {key!r}")
        if key not in cur:
            raise KeyError("missing")
        cur = cur[key]
    return cur


def set_at_path(tree: dict[str, Any], parts: list[str], value: Any) -> None:
    if not parts:
        if not isinstance(value, dict):
            raise DataDictError("root replacement must be a mapping")
        tree.clear()
        tree.update(value)
        return
    cur = tree
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[parts[-1]] = value


def delete_at_path(tree: dict[str, Any], parts: list[str]) -> None:
    if not parts:
        tree.clear()
        return
    cur = tree
    for key in parts[:-1]:
        if not isinstance(cur, dict) or key not in cur:
            return
        cur = cur[key]
        if not isinstance(cur, dict):
            return
    last = parts[-1]
    if isinstance(cur, dict) and last in cur:
        del cur[last]
