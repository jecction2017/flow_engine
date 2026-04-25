"""Filesystem-backed lookup tables (tabular reference data per namespace)."""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

from flow_engine._repo_root import repo_root
from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.stores.profile_store import DEFAULT_PROFILE_ID, active_profile, validate_profile_id


class LookupStoreError(FlowEngineError):
    """Invalid lookup namespace or document shape."""


_NS = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _lookup_dir() -> Path:
    raw = os.environ.get("FLOW_ENGINE_LOOKUP_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root() / "data" / "lookup").resolve()


def validate_lookup_namespace(ns: str) -> str:
    if not ns or not _NS.match(ns):
        raise LookupStoreError(
            "Invalid lookup namespace: use letters, digits, underscore or hyphen (max 64 chars).",
        )
    return ns


def _normalize_cell(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, list):
        return [_normalize_cell(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _normalize_cell(val) for k, val in v.items()}
    return str(v)


def normalize_table(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``fields`` (optional) and ``rows`` (list of flat dicts)."""
    if not isinstance(raw, dict):
        raise LookupStoreError("lookup table must be a JSON object")
    fields = raw.get("fields")
    rows = raw.get("rows")
    if rows is None:
        raise LookupStoreError("missing 'rows'")
    if not isinstance(rows, list):
        raise LookupStoreError("'rows' must be a list")
    out_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise LookupStoreError(f"row {i} must be an object")
        out_rows.append({str(k): _normalize_cell(v) for k, v in row.items()})
    out_fields: list[str]
    if fields is not None:
        if not isinstance(fields, list) or not all(isinstance(x, str) for x in fields):
            raise LookupStoreError("'fields' must be a list of strings")
        out_fields = list(fields)
    else:
        out_fields = []
    if out_rows and not out_fields:
        out_fields = list(out_rows[0].keys())
    return {"fields": out_fields, "rows": out_rows}


_store_cache: tuple[str, "LookupStore"] | None = None


def invalidate_lookup_store_cache() -> None:
    global _store_cache
    _store_cache = None


class LookupStore:
    """One JSON file per namespace under ``profiles/{profile}/{namespace}.json``."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _lookup_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_flat_files()
        self._mtime: dict[str, float] = {}
        self._mem: dict[str, dict[str, Any]] = {}

    def _migrate_legacy_flat_files(self) -> None:
        legacy_files = [p for p in self.directory.glob("*.json") if p.is_file()]
        if not legacy_files:
            return
        target_dir = self.profile_dir(DEFAULT_PROFILE_ID, create=True)
        for p in legacy_files:
            stem = p.stem
            if not _NS.match(stem):
                continue
            dst = target_dir / p.name
            if not dst.exists():
                p.replace(dst)
            else:
                p.unlink()

    @property
    def profiles_dir(self) -> Path:
        return self.directory / "profiles"

    def profile_dir(self, profile_id: str, *, create: bool = False) -> Path:
        pid = validate_profile_id(profile_id)
        p = self.profiles_dir / pid
        if create:
            p.mkdir(parents=True, exist_ok=True)
        return p

    def create_profile(self, profile_id: str) -> None:
        self.profile_dir(profile_id, create=True)

    def _resolve_profile(self, profile_id: str | None) -> str:
        return validate_profile_id(profile_id or active_profile())

    def path_for(self, ns: str, *, profile: str | None = None) -> Path:
        validate_lookup_namespace(ns)
        pid = self._resolve_profile(profile)
        return self.profile_dir(pid, create=True) / f"{ns}.json"

    def list_namespaces(self, *, profile: str | None = None) -> list[str]:
        pid = self._resolve_profile(profile)
        root = self.profile_dir(pid, create=True)
        out: list[str] = []
        for p in sorted(root.glob("*.json")):
            stem = p.stem
            if _NS.match(stem):
                out.append(stem)
        return out

    def exists(self, ns: str, *, profile: str | None = None) -> bool:
        return self.path_for(ns, profile=profile).is_file()

    def read_table(self, ns: str, *, profile: str | None = None) -> dict[str, Any]:
        validate_lookup_namespace(ns)
        pid = self._resolve_profile(profile)
        path = self.path_for(ns, profile=pid)
        cache_key = f"{pid}:{ns}"
        if not path.is_file():
            return {"fields": [], "rows": []}
        mtime = path.stat().st_mtime
        if self._mtime.get(cache_key) == mtime and cache_key in self._mem:
            return copy.deepcopy(self._mem[cache_key])
        data = json.loads(path.read_text(encoding="utf-8"))
        norm = normalize_table(data)
        self._mem[cache_key] = copy.deepcopy(norm)
        self._mtime[cache_key] = mtime
        return copy.deepcopy(norm)

    def write_table(self, ns: str, table: dict[str, Any], *, profile: str | None = None) -> None:
        norm = normalize_table(table)
        pid = self._resolve_profile(profile)
        path = self.path_for(ns, profile=pid)
        cache_key = f"{pid}:{ns}"
        path.write_text(
            json.dumps(norm, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        mtime = path.stat().st_mtime
        self._mem[cache_key] = copy.deepcopy(norm)
        self._mtime[cache_key] = mtime

    def delete_namespace(self, ns: str, *, profile: str | None = None) -> None:
        validate_lookup_namespace(ns)
        pid = self._resolve_profile(profile)
        path = self.path_for(ns, profile=pid)
        cache_key = f"{pid}:{ns}"
        if path.is_file():
            path.unlink()
        self._mem.pop(cache_key, None)
        self._mtime.pop(cache_key, None)


def get_lookup_store() -> LookupStore:
    global _store_cache
    key = str(_lookup_dir())
    if _store_cache is None or _store_cache[0] != key:
        _store_cache = (key, LookupStore())
    return _store_cache[1]
