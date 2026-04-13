"""Load registry.json (manifest for API / 补全)."""

from __future__ import annotations

import json
from typing import Any

from flow_engine.starlark_sdk.paths import REGISTRY_JSON


def load_registry() -> dict[str, Any]:
    if not REGISTRY_JSON.is_file():
        return {"version": "0", "python_functions": [], "internal_modules": []}
    return json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
