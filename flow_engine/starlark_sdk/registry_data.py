"""Load registry.json (manifest for API / 补全)."""

from __future__ import annotations

import json
from typing import Any

from flow_engine.starlark_sdk.builtin_registry import registry_python_doc
from flow_engine.starlark_sdk.paths import REGISTRY_JSON


def load_registry() -> dict[str, Any]:
    # Ensure decorator-based builtin registration side-effects have been loaded.
    from flow_engine.starlark_sdk import python_builtin_impl as _python_builtin_impl  # noqa: F401

    internal_modules: list[dict[str, Any]] = []
    version = "0"
    if REGISTRY_JSON.is_file():
        base = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
        version = str(base.get("version", "0"))
        raw_internal = base.get("internal_modules", [])
        if isinstance(raw_internal, list):
            internal_modules = [m for m in raw_internal if isinstance(m, dict)]
    return {
        "version": version,
        "python_functions": registry_python_doc(),
        "internal_modules": internal_modules,
    }
