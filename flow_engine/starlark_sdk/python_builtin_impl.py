"""MVP 内置 Python 函数实现（注册到 Starlark）。"""

from __future__ import annotations

import json
from typing import Any

from flow_engine.data_dict import lookup as data_dict_lookup
from flow_engine.lookup_service import lookup_query as run_lookup_query
from flow_engine.starlark_sdk.paths import user_scripts_root


def demo_echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": True, "payload": payload}


def demo_add(a: int, b: int) -> int:
    return int(a) + int(b)


def http_simple_get(url: str) -> dict[str, Any]:
    try:
        import urllib.request

        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw
            return {"status": resp.status, "body": body}
    except Exception as exc:  # noqa: BLE001
        return {"status": -1, "error": str(exc)}


def dict_get(path: str, default: Any = None) -> Any:
    """按点路径读取数据字典（``dictionary.yaml``），语义类似 ``dict.get``。"""
    return data_dict_lookup(path, default)


def lookup_query(namespace: str, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # noqa: A002
    """查询 lookup 表（``lookup/{namespace}.json``）。``filter`` 为等值 AND 条件；空则返回全部（有上限）。"""
    return run_lookup_query(namespace, filter)


def user_script_list() -> list[str]:
    """列出 user:// 下已有 .star 相对路径（default/ 为约定租户）。"""
    root = user_scripts_root()
    out: list[str] = []
    for p in sorted(root.rglob("*.star")):
        rel = p.relative_to(root).as_posix()
        out.append(rel)
    return out


# starlark_name -> callable
PYTHON_BUILTINS: dict[str, Any] = {
    "demo_echo": demo_echo,
    "demo_add": demo_add,
    "http_simple_get": http_simple_get,
    "dict_get": dict_get,
    "lookup_query": lookup_query,
    "user_script_list": user_script_list,
}
