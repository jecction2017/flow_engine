"""Resolve internal:// module ids to filesystem paths.

user:// 脚本已迁移到 MySQL (fe_user_script)，由 starlark_sdk/loader.py 中的
_load_module_content() 直接从数据库读取内容，不再解析为文件路径。
"""

from __future__ import annotations

import re
from pathlib import Path

from flow_engine.starlark_sdk.paths import INTERNAL_ROOT

_SAFE_REL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_./-]*\.star$")


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


def resolve_module_uri(module_id: str) -> Path:
    """Resolve internal:// URI to a filesystem Path.

    user:// 已迁移到 MySQL，调用此函数时请改用 loader._load_module_content()。
    """
    if module_id.startswith("internal://"):
        rel = module_id.removeprefix("internal://").lstrip("/")
        return resolve_internal_script_file(rel)
    if module_id.startswith("user://"):
        raise ValueError(
            "user:// modules are stored in MySQL; "
            "use starlark_sdk.loader._load_module_content() instead of resolve_module_uri()"
        )
    raise ValueError(f"unsupported module id: {module_id!r}")
