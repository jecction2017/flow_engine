"""Locate the repository root (directory containing pyproject.toml)."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Return checkout root, or raise if it cannot be determined."""
    raw = os.environ.get("FLOW_ENGINE_REPO_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    here = Path(__file__).resolve().parent
    for p in (here, *here.parents):
        if (p / "pyproject.toml").is_file():
            return p
    msg = (
        "Cannot find flow_engine repository root (no pyproject.toml in parents). "
        "Set FLOW_ENGINE_REPO_ROOT, or set per-resource env vars "
        "(FLOW_ENGINE_FLOWS_DIR, FLOW_ENGINE_LOOKUP_DIR, etc.)."
    )
    raise RuntimeError(msg)
