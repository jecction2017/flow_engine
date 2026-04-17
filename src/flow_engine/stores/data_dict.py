"""Runtime access to the data dictionary (Starlark ``dict_get`` / flow global seed)."""

from __future__ import annotations

import copy
from typing import Any

from flow_engine.stores.dict_store import DataDictStore, _dict_dir, delete_at_path, get_at_path, parse_path, set_at_path

_store_cache: tuple[str, DataDictStore] | None = None


def invalidate_store_cache() -> None:
    global _store_cache
    _store_cache = None


def store() -> DataDictStore:
    global _store_cache
    key = str(_dict_dir())
    if _store_cache is None or _store_cache[0] != key:
        _store_cache = (key, DataDictStore())
    return _store_cache[1]


def tree_copy() -> dict[str, Any]:
    """Deep copy of current dictionary tree (for ``$.global.dictionary`` snapshot)."""
    return store().read_tree()


def lookup(path: str, default: Any = None) -> Any:
    """Dot-path lookup, same semantics as ``dict.get`` for missing keys."""
    from flow_engine.stores.dict_store import DataDictError

    parts = parse_path(path)
    if not parts:
        return default
    try:
        tree = store().read_tree()
        return get_at_path(tree, parts)
    except (KeyError, DataDictError):
        return default


def apply_subtree_yaml(path: str, yaml_fragment: str) -> dict[str, Any]:
    """Parse YAML fragment and replace subtree at ``path`` (empty path = whole root)."""
    import yaml

    from flow_engine.stores.dict_store import DataDictError

    parts = parse_path(path)
    if not yaml_fragment.strip():
        value: Any = {}
    else:
        value = yaml.safe_load(yaml_fragment)
    st = store()
    tree = st.read_tree()
    if not parts:
        if not isinstance(value, dict):
            raise DataDictError("root must be a mapping when path is empty")
        new_root = copy.deepcopy(value)
        st.write_tree(new_root)
        return new_root
    set_at_path(tree, parts, value)
    st.write_tree(tree)
    return tree


def delete_path(path: str) -> dict[str, Any]:
    parts = parse_path(path)
    st = store()
    tree = st.read_tree()
    delete_at_path(tree, parts)
    st.write_tree(tree)
    return tree


def subtree_as_yaml(path: str) -> str:
    """Return pretty YAML for the subtree at ``path`` (empty = full document)."""
    import yaml

    from flow_engine.stores.dict_store import DataDictError

    tree = store().read_tree()
    parts = parse_path(path)
    if not parts:
        sub: Any = tree
    else:
        try:
            sub = get_at_path(tree, parts)
        except KeyError as e:
            raise DataDictError(f"Path not found: {path}") from e
    return yaml.safe_dump(sub, sort_keys=False, allow_unicode=True, default_flow_style=False)
