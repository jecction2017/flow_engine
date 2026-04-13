"""Starlark FileLoader with FrozenModule cache (internal:// / user://)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import starlark as sl

from flow_engine.starlark_sdk.uri_resolve import resolve_module_uri


def _globals_for_loaded_module() -> sl.Globals:
    return sl.Globals.extended_by([sl.LibraryExtension.Json])


def build_file_loader() -> tuple[sl.FileLoader, dict[str, sl.FrozenModule]]:
    cache: dict[str, sl.FrozenModule] = {}

    def load_fn(module_id: str) -> sl.FrozenModule:
        if module_id in cache:
            return cache[module_id]
        path: Path = resolve_module_uri(module_id)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        inner = sl.Module()
        ast = sl.parse(str(path), path.read_text(encoding="utf-8"))
        glb = _globals_for_loaded_module()
        loader = sl.FileLoader(load_fn)
        sl.eval(inner, ast, glb, file_loader=loader)
        frozen = inner.freeze()
        cache[module_id] = frozen
        return frozen

    return sl.FileLoader(load_fn), cache


def dialect_with_load() -> sl.Dialect:
    d = sl.Dialect.standard()
    d.enable_load = True
    return d
