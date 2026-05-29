"""MVP 内置 Python 函数实现（注册到 Starlark）。"""

from __future__ import annotations

from typing import Any

from flow_engine.lookup.lookup_service import lookup_query as run_lookup_query
from flow_engine.stores.data_dict import lookup as data_dict_lookup
from flow_engine.starlark_sdk.builtin_registry import (
    BuiltinArgSpec,
    PythonBuiltinSpec,
    builtin_map,
    register_builtin,
)
from flow_engine.starlark_sdk.runtime import get_redirect_params


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
        id="python://dict/get",
        starlark_name="dict_get",
        category="dictionary",
        summary="按点路径读取当前已解析数据字典，缺省返回 default，等同 dict.get 语义",
        signature=(
            BuiltinArgSpec(name="path", type="str"),
            BuiltinArgSpec(name="default", type="any", required=False),
        ),
        returns="any",
        side_effects="disk",
        suppress_result=None,
    )
)
def dict_get(path: str, default: Any = None) -> Any:
    """按点路径读取当前运行的已解析数据字典，语义类似 ``dict.get``。"""
    return data_dict_lookup(path, default)


@register_builtin(
    PythonBuiltinSpec(
        id="python://lookup/query",
        starlark_name="lookup_query",
        category="lookup",
        summary="查询 lookup 表（profiles/{profile}/{namespace}.json）；filter 为等值 AND；空 filter 返回全部（有上限）",
        signature=(
            BuiltinArgSpec(name="namespace", type="str"),
            BuiltinArgSpec(name="filter", type="dict", required=False),
        ),
        returns="list",
        side_effects="disk",
        suppress_result=[],
    )
)
def lookup_query(namespace: str, filter: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # noqa: A002
    """查询 lookup 表（``lookup/profiles/{profile}/{namespace}.json``）。"""
    return run_lookup_query(namespace, filter)


@register_builtin(
    PythonBuiltinSpec(
        id="python://user/list_scripts",
        starlark_name="user_script_list",
        category="user",
        summary="列出 starlark_user 下用户 .star 相对路径",
        returns="list",
        side_effects="disk",
        suppress_result=[],
    )
)
def user_script_list() -> list[str]:
    """列出 MySQL fe_user_script 中所有未删除脚本的 'tenant/rel_path' 路径。"""
    from flow_engine.starlark_sdk.user_script_store import get_user_script_store

    return get_user_script_store().list_rel_paths()



@register_builtin(
    PythonBuiltinSpec(
        id="python://system/sleep",
        starlark_name="system_sleep",
        category="system",
        summary="睡眠指定秒数",
        signature=(BuiltinArgSpec(name="seconds", type="int"),),
        returns="int",
        side_effects="none",
    )
)
def system_sleep(seconds: int) -> dict[str, Any]:
    import time
    time.sleep(seconds)
    return seconds


@register_builtin(
    PythonBuiltinSpec(
        id="python://runtime/log",
        starlark_name="log",
        category="runtime",
        summary="记录运行时调试日志，支持 level 参数",
        signature=(
            BuiltinArgSpec(name="args", type="any", required=False),
            BuiltinArgSpec(name="level", type="str", required=False),
        ),
        returns="none",
        side_effects="none",
    )
)
def runtime_log(*args: Any, level: str = "info") -> None:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.runtime_log(*args, level=level)


@register_builtin(
    PythonBuiltinSpec(
        id="python://runtime/log_info",
        starlark_name="log_info",
        category="runtime",
        summary="记录 info 级别调试日志",
        signature=(BuiltinArgSpec(name="args", type="any", required=False),),
        returns="none",
        side_effects="none",
    )
)
def runtime_log_info(*args: Any) -> None:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.runtime_log_info(*args)


@register_builtin(
    PythonBuiltinSpec(
        id="python://runtime/log_warn",
        starlark_name="log_warn",
        category="runtime",
        summary="记录 warn 级别调试日志",
        signature=(BuiltinArgSpec(name="args", type="any", required=False),),
        returns="none",
        side_effects="none",
    )
)
def runtime_log_warn(*args: Any) -> None:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.runtime_log_warn(*args)


@register_builtin(
    PythonBuiltinSpec(
        id="python://runtime/log_error",
        starlark_name="log_error",
        category="runtime",
        summary="记录 error 级别调试日志",
        signature=(BuiltinArgSpec(name="args", type="any", required=False),),
        returns="none",
        side_effects="none",
    )
)
def runtime_log_error(*args: Any) -> None:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.runtime_log_error(*args)


@register_builtin(
    PythonBuiltinSpec(
        id="python://runtime/log_debug",
        starlark_name="log_debug",
        category="runtime",
        summary="记录 debug 级别调试日志",
        signature=(BuiltinArgSpec(name="args", type="any", required=False),),
        returns="none",
        side_effects="none",
    )
)
def runtime_log_debug(*args: Any) -> None:
    from flow_engine.starlark_sdk import runtime as sdk_runtime

    return sdk_runtime.runtime_log_debug(*args)


# starlark_name -> callable
PYTHON_BUILTINS: dict[str, Any] = builtin_map()



@register_builtin(
    PythonBuiltinSpec(
        id="python://probe/side_effect",
        starlark_name="side_effect_probe",
        category="integration",  # 关键：用 integration，让 DEBUG 默认就会 SUPPRESS
        summary="Side-effect probe builtin used for end-to-end capability testing.",
        signature=(),
        returns="dict",
        side_effects="network",
        suppress_result={"_suppressed": True, "called": False, "via": "suppress_result"},
    )
)
def side_effect_probe(arg: str = "default") -> dict[str, Any]:
    """
    This builtin simulates a side-effectful call. It is intentionally in
    integration category so RunMode.DEBUG will suppress by default.
    REDIRECT params are read via get_redirect_params().
    """
    rp = get_redirect_params() or {}
    # 这里故意不做真实网络/DB，只把“本来要做副作用”的信息返回给脚本用于断言
    return {
        "_suppressed": False,
        "called": True,
        "arg": arg,
        "redirect": dict(rp),
    }


# Register flow/context/util and integration builtins.
from flow_engine.starlark_sdk import runtime_builtins as _runtime_builtins  # noqa: E402, F401
from flow_engine.starlark_sdk import integrations as _integrations  # noqa: E402, F401