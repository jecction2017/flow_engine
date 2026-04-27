"""Resolved data dictionary access for Starlark and flow globals."""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from flow_engine.stores.dict_store import (
    DEFAULT_PROFILE_ID,
    DataDictError,
    DataDictStore,
    get_at_path,
    parse_path,
    set_at_path,
    validate_profile_id,
)

_store_cache: DataDictStore | None = None
_active_dictionary: ContextVar[dict[str, Any] | None] = ContextVar(
    "flow_engine_active_dictionary", default=None
)


def invalidate_store_cache() -> None:
    global _store_cache
    _store_cache = None


def store() -> DataDictStore:
    global _store_cache
    if _store_cache is None:
        _store_cache = DataDictStore()
    return _store_cache


def deep_merge(base: Any, override: Any) -> Any:
    """Merge dictionaries recursively; lists/scalars are replaced wholesale."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = copy.deepcopy(base)
        for k, v in override.items():
            if k in out:
                out[k] = deep_merge(out[k], v)
            else:
                out[k] = copy.deepcopy(v)
        return out
    return copy.deepcopy(override)


def _canonical_hash(data: dict[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _module_sort_key(module_id: str) -> tuple[int, str]:
    return (module_id.count("."), module_id)


def _read_layer_modules(profile_id: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    st = store()
    base_modules: dict[str, dict[str, Any]] = {}
    records: dict[str, dict[str, Any]] = {}

    for mod in st.list_modules("base"):
        tree = st.read_module("base", mod.module_id)
        base_modules[mod.module_id] = tree
        records[mod.module_id] = {
            "module_id": mod.module_id,
            "base_path": mod.path,
            "profile_path": None,
            "from_base": True,
            "from_profile": False,
        }

    # Profile existence is part of the contract: no implicit fallback.
    st.ensure_profile(profile_id)
    for mod in st.list_modules("profile", profile=profile_id):
        tree = st.read_module("profile", mod.module_id, profile=profile_id)
        if mod.module_id in base_modules:
            base_modules[mod.module_id] = deep_merge(base_modules[mod.module_id], tree)
        else:
            base_modules[mod.module_id] = copy.deepcopy(tree)
        rec = records.setdefault(
            mod.module_id,
            {
                "module_id": mod.module_id,
                "base_path": None,
                "profile_path": None,
                "from_base": False,
                "from_profile": False,
            },
        )
        rec["profile_path"] = mod.path
        rec["from_profile"] = True

    return base_modules, [records[k] for k in sorted(records)]


def resolve(profile_id: str | None = None, runtime_patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a profile into the final dictionary tree and metadata."""
    profile = validate_profile_id(profile_id or DEFAULT_PROFILE_ID)
    if runtime_patch is not None and not isinstance(runtime_patch, dict):
        raise DataDictError("runtime_patch root must be a mapping (object)")

    modules, module_records = _read_layer_modules(profile)
    tree: dict[str, Any] = {}
    for module_id in sorted(modules, key=_module_sort_key):
        module_tree = modules[module_id]
        parts = parse_path(module_id)
        if not parts:
            tree = deep_merge(tree, module_tree)
        else:
            try:
                current = get_at_path(tree, parts)
            except (KeyError, DataDictError):
                set_at_path(tree, parts, copy.deepcopy(module_tree))
            else:
                set_at_path(tree, parts, deep_merge(current, module_tree))

    if runtime_patch:
        tree = deep_merge(tree, runtime_patch)

    return {
        "resolved_dictionary": tree,
        "resolved_profile": profile,
        "resolved_modules": module_records,
        "resolved_hash": _canonical_hash(tree),
    }


def tree_copy(
    profile_id: str | None = None,
    runtime_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deep copy of the resolved dictionary tree for ``$.global.dictionary``."""
    return copy.deepcopy(resolve(profile_id, runtime_patch)["resolved_dictionary"])


def active_dictionary() -> dict[str, Any] | None:
    cur = _active_dictionary.get()
    return copy.deepcopy(cur) if cur is not None else None


@contextmanager
def dictionary_scope(dictionary: dict[str, Any]) -> Iterator[None]:
    token = _active_dictionary.set(copy.deepcopy(dictionary))
    try:
        yield
    finally:
        _active_dictionary.reset(token)


def lookup(path: str, default: Any = None) -> Any:
    """Dot-path lookup from the active run dictionary, falling back to default profile."""
    parts = parse_path(path)
    if not parts:
        return default
    try:
        tree = _active_dictionary.get()
        if tree is None:
            tree = tree_copy(DEFAULT_PROFILE_ID)
        return get_at_path(tree, parts)
    except (KeyError, DataDictError):
        return default
