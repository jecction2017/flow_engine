"""MVP 内置 Python 函数实现（注册到 Starlark）。"""

from __future__ import annotations

import json
from typing import Any

from flow_engine.lookup.lookup_service import lookup_query as run_lookup_query
from flow_engine.stores.data_dict import lookup as data_dict_lookup
from flow_engine.starlark_sdk.builtin_registry import (
    BuiltinArgSpec,
    PythonBuiltinSpec,
    builtin_map,
    register_builtin,
)
from flow_engine.starlark_sdk.paths import user_scripts_root


@register_builtin(
    PythonBuiltinSpec(
        id="python://demo/echo",
        starlark_name="demo_echo",
        category="demo",
        summary="回显 dict，用于验证注册与补全元数据",
        signature=(BuiltinArgSpec(name="payload", type="dict"),),
        returns="dict",
        side_effects="none",
    )
)
def demo_echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": True, "payload": payload}


@register_builtin(
    PythonBuiltinSpec(
        id="python://demo/add",
        starlark_name="demo_add",
        category="demo",
        summary="整数相加",
        signature=(BuiltinArgSpec(name="a", type="int"), BuiltinArgSpec(name="b", type="int")),
        returns="int",
        side_effects="none",
    )
)
def demo_add(a: int, b: int) -> int:
    return int(a) + int(b)


@register_builtin(
    PythonBuiltinSpec(
        id="python://http/simple_get",
        starlark_name="http_simple_get",
        category="integration",
        summary="受控 HTTP GET（超时、仅 JSON/文本），MVP 占位",
        signature=(BuiltinArgSpec(name="url", type="str"),),
        returns="dict",
        side_effects="network",
    )
)
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


@register_builtin(
    PythonBuiltinSpec(
        id="python://dict/get",
        starlark_name="dict_get",
        category="dictionary",
        summary="按点路径读取数据字典（dictionary.yaml），缺省返回 default，等同 dict.get 语义",
        signature=(
            BuiltinArgSpec(name="path", type="str"),
            BuiltinArgSpec(name="default", type="any", required=False),
        ),
        returns="any",
        side_effects="disk",
    )
)
def dict_get(path: str, default: Any = None) -> Any:
    """按点路径读取数据字典（``dictionary.yaml``），语义类似 ``dict.get``。"""
    return data_dict_lookup(path, default)


@register_builtin(
    PythonBuiltinSpec(
        id="python://lookup/query",
        starlark_name="lookup_query",
        category="lookup",
        summary="查询 lookup 表（lookup/{namespace}.json）；filter 为等值 AND；空 filter 返回全部（有上限）",
        signature=(
            BuiltinArgSpec(name="namespace", type="str"),
            BuiltinArgSpec(name="filter", type="dict", required=False),
        ),
        returns="list",
        side_effects="disk",
    )
)
def lookup_query(namespace: str, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # noqa: A002
    """查询 lookup 表（``lookup/{namespace}.json``）。``filter`` 为等值 AND 条件；空则返回全部（有上限）。"""
    return run_lookup_query(namespace, filter)


@register_builtin(
    PythonBuiltinSpec(
        id="python://user/list_scripts",
        starlark_name="user_script_list",
        category="user",
        summary="列出 starlark_user 下用户 .star 相对路径",
        returns="list",
        side_effects="disk",
    )
)
def user_script_list() -> list[str]:
    """列出 user:// 下已有 .star 相对路径（default/ 为约定租户）。"""
    root = user_scripts_root()
    out: list[str] = []
    for p in sorted(root.rglob("*.star")):
        rel = p.relative_to(root).as_posix()
        out.append(rel)
    return out


# starlark_name -> callable
PYTHON_BUILTINS: dict[str, Any] = builtin_map()
