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
    """One JSON file per namespace: ``{namespace}.json``."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _lookup_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._mtime: dict[str, float] = {}
        self._mem: dict[str, dict[str, Any]] = {}

    def path_for(self, ns: str) -> Path:
        validate_lookup_namespace(ns)
        return self.directory / f"{ns}.json"

    def list_namespaces(self) -> list[str]:
        out: list[str] = []
        for p in sorted(self.directory.glob("*.json")):
            stem = p.stem
            if _NS.match(stem):
                out.append(stem)
        return out

    def exists(self, ns: str) -> bool:
        return self.path_for(ns).is_file()

    def read_table(self, ns: str) -> dict[str, Any]:
        validate_lookup_namespace(ns)
        path = self.path_for(ns)
        if not path.is_file():
            return {"fields": [], "rows": []}
        mtime = path.stat().st_mtime
        if self._mtime.get(ns) == mtime and ns in self._mem:
            return copy.deepcopy(self._mem[ns])
        data = json.loads(path.read_text(encoding="utf-8"))
        norm = normalize_table(data)
        self._mem[ns] = copy.deepcopy(norm)
        self._mtime[ns] = mtime
        return copy.deepcopy(norm)

    def write_table(self, ns: str, table: dict[str, Any]) -> None:
        norm = normalize_table(table)
        path = self.path_for(ns)
        path.write_text(
            json.dumps(norm, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        mtime = path.stat().st_mtime
        self._mem[ns] = copy.deepcopy(norm)
        self._mtime[ns] = mtime

    def delete_namespace(self, ns: str) -> None:
        validate_lookup_namespace(ns)
        path = self.path_for(ns)
        if path.is_file():
            path.unlink()
        self._mem.pop(ns, None)
        self._mtime.pop(ns, None)


def get_lookup_store() -> LookupStore:
    global _store_cache
    key = str(_lookup_dir())
    if _store_cache is None or _store_cache[0] != key:
        _store_cache = (key, LookupStore())
    return _store_cache[1]
