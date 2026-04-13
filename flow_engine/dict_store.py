"""YAML-backed hierarchical data dictionary (system / middleware / business config)."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from flow_engine.exceptions import FlowEngineError


class DataDictError(FlowEngineError):
    """Invalid dictionary file or path."""


def _dict_dir() -> Path:
    raw = os.environ.get("FLOW_ENGINE_DICT_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "dict").resolve()


class DataDictStore:
    """Single-document store: ``dictionary.yaml`` mapping at root."""

    FILENAME = "dictionary.yaml"

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or _dict_dir()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._cached_tree: dict[str, Any] | None = None
        self._cached_mtime: float | None = None

    def yaml_path(self) -> Path:
        return self.directory / self.FILENAME

    def read_raw(self) -> str:
        p = self.yaml_path()
        if not p.is_file():
            return "{}\n"
        return p.read_text(encoding="utf-8")

    def read_tree(self) -> dict[str, Any]:
        p = self.yaml_path()
        if not p.is_file():
            self._cached_tree = {}
            self._cached_mtime = None
            return {}
        mtime = p.stat().st_mtime
        if self._cached_mtime == mtime and self._cached_tree is not None:
            return copy.deepcopy(self._cached_tree)
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            data: Any = {}
        else:
            data = yaml.safe_load(raw)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise DataDictError("dictionary.yaml root must be a mapping (object)")
        self._cached_tree = copy.deepcopy(data)
        self._cached_mtime = mtime
        return copy.deepcopy(data)

    def write_raw(self, text: str) -> None:
        if not text.strip():
            data: Any = {}
        else:
            data = yaml.safe_load(text)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise DataDictError("dictionary.yaml root must be a mapping (object)")
        p = self.yaml_path()
        out = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
        p.write_text(out, encoding="utf-8", newline="\n")
        self._cached_tree = copy.deepcopy(data)
        self._cached_mtime = p.stat().st_mtime

    def write_tree(self, tree: dict[str, Any]) -> None:
        if not isinstance(tree, dict):
            raise DataDictError("root must be a dict")
        p = self.yaml_path()
        out = yaml.safe_dump(tree, sort_keys=False, allow_unicode=True, default_flow_style=False)
        p.write_text(out, encoding="utf-8", newline="\n")
        self._cached_tree = copy.deepcopy(tree)
        self._cached_mtime = p.stat().st_mtime


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
