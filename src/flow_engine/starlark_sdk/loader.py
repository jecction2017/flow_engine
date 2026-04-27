"""Starlark module loader with FrozenModule cache.

Supported schemes:
  internal://lib/helpers.star  → 从包内 starlib/internal/ 读取（文件系统）
  user://<tenant>/<path>.star  → 从 MySQL fe_user_script 表读取
"""

from __future__ import annotations

import threading
from typing import Any

import starlark as sl

from flow_engine.starlark_sdk.uri_resolve import resolve_internal_script_file


def _globals_for_loaded_module() -> sl.Globals:
    return sl.Globals.extended_by([sl.LibraryExtension.Json])


def _load_module_content(module_id: str) -> tuple[str, str]:
    """Return (source_code, display_filename) for any supported module URI.

    internal:// → 从包内文件系统读取
    user://     → 从 MySQL fe_user_script 读取
    """
    if module_id.startswith("internal://"):
        rel = module_id.removeprefix("internal://").lstrip("/")
        path = resolve_internal_script_file(rel)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path.read_text(encoding="utf-8"), str(path)

    if module_id.startswith("user://"):
        rest = module_id.removeprefix("user://").lstrip("/")
        if "/" not in rest:
            raise ValueError("user:// expects user://<tenant>/<path>.star")
        tenant, rel = rest.split("/", 1)
        if not rel.endswith(".star"):
            raise ValueError("user module must end with .star")
        # 延迟导入，避免循环
        from flow_engine.starlark_sdk.user_script_store import get_user_script_store

        content = get_user_script_store().get_script(tenant, rel)
        return content, module_id

    raise ValueError(f"unsupported module URI: {module_id!r}")


class ModuleLoaderCache:
    """Thread-safe reusable loader/cache for loaded Starlark modules."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, sl.FrozenModule] = {}
        self._hits = 0
        self._misses = 0
        self._loader = sl.FileLoader(self._load_fn)

    def _load_fn(self, module_id: str) -> sl.FrozenModule:
        with self._lock:
            if module_id in self._cache:
                self._hits += 1
                return self._cache[module_id]
            self._misses += 1

        content, display_path = _load_module_content(module_id)
        inner = sl.Module()
        ast = sl.parse(display_path, content, dialect=dialect_with_load())
        glb = _globals_for_loaded_module()
        sl.eval(inner, ast, glb, file_loader=self._loader)
        frozen = inner.freeze()
        with self._lock:
            self._cache[module_id] = frozen
        return frozen

    def get_loader(self) -> sl.FileLoader:
        return self._loader

    def warmup(self, module_ids: list[str]) -> dict[str, Any]:
        loaded = 0
        errors: list[dict[str, str]] = []
        uniq = list(dict.fromkeys(module_ids))
        for module_id in uniq:
            try:
                self._load_fn(module_id)
                loaded += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({"module_id": module_id, "error": str(exc)})
        return {"requested": len(uniq), "loaded": loaded, "errors": errors}

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_ratio = (self._hits / total) if total else 0.0
            return {
                "cached_modules": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": round(hit_ratio, 4),
            }


_LOADER_CACHE = ModuleLoaderCache()


def build_file_loader() -> tuple[sl.FileLoader, dict[str, sl.FrozenModule]]:
    return _LOADER_CACHE.get_loader(), {}


def warmup_modules(module_ids: list[str]) -> dict[str, Any]:
    return _LOADER_CACHE.warmup(module_ids)


def loader_stats() -> dict[str, Any]:
    return _LOADER_CACHE.stats()


def clear_loader_cache() -> None:
    _LOADER_CACHE.clear()


def dialect_with_load() -> sl.Dialect:
    d = sl.Dialect.standard()
    d.enable_load = True
    return d
