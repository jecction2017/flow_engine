"""Flow-control, context, and utility builtins exposed to Starlark scripts."""

from __future__ import annotations

import re
from typing import Any

from flow_engine.engine.exceptions import (
    BreakInterrupt,
    ContinueInterrupt,
    JumpTarget,
    TerminateInterrupt,
)
from flow_engine.starlark_sdk.builtin_registry import (
    ATTACH_CONTEXT,
    ATTACH_FLOW_CONTROL,
    BuiltinArgSpec,
    PythonBuiltinSpec,
    register_builtin,
)


def _cf_raise(exc: BaseException) -> None:
    from flow_engine.engine.starlark_glue import _cf_set

    _cf_set(exc)
    raise exc


@register_builtin(
    PythonBuiltinSpec(
        id="python://flow/jump",
        starlark_name="flow_jump",
        category="flow",
        summary="跳转到同层兄弟节点（target 为节点 id）；未解析的目标在运行期记为 FAILED",
        signature=(BuiltinArgSpec(name="target", type="str"),),
        returns="none",
        side_effects="none",
        attach_mode=ATTACH_FLOW_CONTROL,
    )
)
def flow_jump(target: str) -> None:
    _cf_raise(JumpTarget(str(target)))


@register_builtin(
    PythonBuiltinSpec(
        id="python://flow/continue",
        starlark_name="flow_continue",
        category="flow",
        summary="在 LOOP 迭代中跳过当前项的 collect，继续下一项",
        signature=(),
        returns="none",
        side_effects="none",
        attach_mode=ATTACH_FLOW_CONTROL,
    )
)
def flow_continue() -> None:
    _cf_raise(ContinueInterrupt())


@register_builtin(
    PythonBuiltinSpec(
        id="python://flow/break",
        starlark_name="flow_break",
        category="flow",
        summary="在 LOOP 中提前结束循环",
        signature=(),
        returns="none",
        side_effects="none",
        attach_mode=ATTACH_FLOW_CONTROL,
    )
)
def flow_break() -> None:
    _cf_raise(BreakInterrupt())


@register_builtin(
    PythonBuiltinSpec(
        id="python://flow/terminate",
        starlark_name="flow_terminate",
        category="flow",
        summary="终止当前任务节点执行（跳过重试）",
        signature=(),
        returns="none",
        side_effects="none",
        attach_mode=ATTACH_FLOW_CONTROL,
    )
)
def flow_terminate() -> None:
    _cf_raise(TerminateInterrupt())


@register_builtin(
    PythonBuiltinSpec(
        id="python://util/regex_match",
        starlark_name="regex_match",
        category="util",
        summary="正则匹配：pattern 在 text 中命中返回 True，否则 False",
        signature=(
            BuiltinArgSpec(name="pattern", type="str"),
            BuiltinArgSpec(name="text", type="str"),
        ),
        returns="bool",
        side_effects="none",
    )
)
def regex_match(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


@register_builtin(
    PythonBuiltinSpec(
        id="python://context/resolve",
        starlark_name="resolve",
        category="context",
        summary='按 $. 路径读取运行时上下文（如 resolve("$.global.order.id")）；循环 iterable 可简写为 $.global.items',
        signature=(BuiltinArgSpec(name="path", type="str"),),
        returns="any",
        side_effects="none",
        attach_mode=ATTACH_CONTEXT,
    )
)
def resolve(path: str) -> Any:
    """Registry placeholder; :func:`inject_resolve` binds the real callable per eval."""
    raise RuntimeError("resolve() is only available during script evaluation")
