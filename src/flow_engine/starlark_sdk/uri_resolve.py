"""Resolve internal:// and user:// module ids to filesystem paths."""

from __future__ import annotations

import re
from pathlib import Path

from flow_engine.starlark_sdk.paths import INTERNAL_ROOT, user_scripts_root

_SAFE_REL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./-]*\.star$")
_TENANT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def _internal_root_candidates() -> list[Path]:
    """Support editable/source layouts and fallback to current workspace."""
    roots: list[Path] = [INTERNAL_ROOT.resolve()]
    cwd = Path.cwd().resolve()
    roots.extend(
        [
            (cwd / "flow_engine" / "starlib" / "internal").resolve(),
            (cwd / "starlib" / "internal").resolve(),
        ]
    )
    uniq: list[Path] = []
    for r in roots:
        if r not in uniq:
            uniq.append(r)
    return uniq


def resolve_internal_script_file(rel: str) -> Path:
    """Resolve path relative to INTERNAL_ROOT (e.g. lib/helpers.star)."""
    if not _SAFE_REL.match(rel):
        raise ValueError("invalid internal script path")
    fallback: Path | None = None
    for root in _internal_root_candidates():
        path = (root / rel).resolve()
        if not str(path).startswith(str(root)):
            continue
        if fallback is None:
            fallback = path
        if path.is_file():
            return path
    if fallback is None:
        raise ValueError("internal path escapes root")
    return fallback


def resolve_user_script_file(tenant: str, rel: str) -> Path:
    """Resolve tenant + relative path under user_scripts_root(); raises ValueError if unsafe."""
    if not _TENANT.match(tenant):
        raise ValueError("invalid tenant")
    if not _SAFE_REL.match(rel):
        raise ValueError("invalid script path")
    base = (user_scripts_root() / tenant).resolve()
    path = (base / rel).resolve()
    if not str(path).startswith(str(base)):
        raise ValueError("path escapes tenant root")
    return path


def resolve_module_uri(module_id: str) -> Path:
    if module_id.startswith("internal://"):
        rel = module_id.removeprefix("internal://").lstrip("/")
        return resolve_internal_script_file(rel)
    if module_id.startswith("user://"):
        rest = module_id.removeprefix("user://").lstrip("/")
        if "/" not in rest:
            raise ValueError("user:// expects user://<tenant>/<path>.star")
        tenant, rel = rest.split("/", 1)
        if not rel.endswith(".star"):
            raise ValueError("user module must end with .star")
        if not _SAFE_REL.match(rel):
            raise ValueError("invalid user script path")
        base = (user_scripts_root() / tenant).resolve()
        path = (base / rel).resolve()
        if not str(path).startswith(str(base)):
            raise ValueError("user path escapes tenant root")
        return path
    raise ValueError(f"unsupported module id: {module_id!r}")
