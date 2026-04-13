"""Filesystem roots for internal / user Starlark assets."""

from __future__ import annotations

import os
from pathlib import Path

# 包内目录：flow_engine/starlib/
PACKAGE_DIR = Path(__file__).resolve().parent.parent
STARLIB_DIR = PACKAGE_DIR / "starlib"
INTERNAL_ROOT = STARLIB_DIR / "internal"
REGISTRY_JSON = STARLIB_DIR / "registry.json"

# 仓库根目录（假设包位于 <repo>/flow_engine/）
REPO_ROOT = PACKAGE_DIR.parent


def user_scripts_root() -> Path:
    raw = os.environ.get("FLOW_ENGINE_STARLARK_USER", "").strip()
    base = Path(raw).expanduser().resolve() if raw else (REPO_ROOT / "starlark_user").resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base
