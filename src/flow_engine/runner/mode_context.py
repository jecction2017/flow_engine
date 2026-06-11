"""CapabilityPolicy three-layer context (system default + deployment + node).

设计文档 §4。所有副作用 builtin 调用 :func:`check_capability` 决定
``allow / suppress / redirect``；``REDIRECT`` 由 builtin 自行解析
``redirect_params`` 处理。

ContextVar 是 asyncio + thread-local 双重隔离的：
* 同一 event loop 上不同 Task 互不可见（asyncio Task 在创建时复制 contextvars 快照）
* 多线程时每条线程独立。

约定：``run_mode_scope`` 在 ``FlowRuntime.run()`` 入口设置一次，
``node_capability_scope`` 在每个 TaskNode 进入 / 离开时 push/pop 节点级覆盖。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from flow_engine.runner.models import (
    CapabilityAction,
    CapabilityRule,
    RunMode,
)

# ---------------------------------------------------------------------------
# 系统默认策略：debug/shadow 抑制对外副作用 builtin，production 全部 allow。
#
# Category 命名约定（与 PythonBuiltinSpec.category 必须一致）：
# - ``integration``  外部集成（HTTP / 第三方 API）。默认在 debug/shadow 下 SUPPRESS。
# - ``db_write``     未来 DB 写 builtin 的占位类目。
# - ``mq_publish``   未来 MQ 发布 builtin 的占位类目。
# - ``dictionary`` / ``lookup`` / ``user`` / ``demo`` / ``system`` / ``runtime``
#                    属于读类或本地无副作用类，默认 ALLOW。
# 调整时需同步检查 ``python_builtin_impl.py`` 各 spec 的 category 是否在白名单。
# ---------------------------------------------------------------------------

_SYSTEM_DEFAULT_POLICY: dict[RunMode, list[CapabilityRule]] = {
    RunMode.DEBUG: [
        CapabilityRule(builtin_category="db_read", action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="db_write", action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="mq_publish", action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="integration", action=CapabilityAction.SUPPRESS),
    ],
    RunMode.SHADOW: [
        CapabilityRule(builtin_category="db_read", action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="db_write", action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="mq_publish", action=CapabilityAction.SUPPRESS),
        CapabilityRule(builtin_category="integration", action=CapabilityAction.SUPPRESS),
    ],
    RunMode.PRODUCTION: [],
}


def system_default_policy(mode: RunMode) -> list[CapabilityRule]:
    """供测试 / 可观测性使用的快照。返回新列表，调用方不可改写共享实例。"""
    return [r.model_copy() for r in _SYSTEM_DEFAULT_POLICY.get(mode, [])]


# ---------------------------------------------------------------------------
# ContextVar
# ---------------------------------------------------------------------------


@dataclass
class _CapCtx:
    mode: RunMode = RunMode.PRODUCTION
    base_rules: list[CapabilityRule] = field(default_factory=list)
    # node_rules 用栈结构以支持嵌套（虽然当前实现仅 TaskNode 一层 push）
    node_stack: list[list[CapabilityRule]] = field(default_factory=list)


_cap_ctx_var: ContextVar[_CapCtx] = ContextVar("_flow_engine_cap_ctx", default=_CapCtx())


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


@contextmanager
def run_mode_scope(
    mode: RunMode,
    deployment_rules: list[CapabilityRule] | None = None,
    profile_system_rules: list[CapabilityRule] | None = None,
) -> Iterator[None]:
    """在 ``FlowRuntime.run()`` 入口处调用，建立 base_rules。

    base_rules 顺序（高优先级 → 低优先级）：
        deployment_rules ++ profile_system_rules ++ system_default_policy[mode]

    - ``deployment_rules``：单次部署 / 试运行 / 测试批次显式传入。
    - ``profile_system_rules``：环境级（``fe_env_profile.system_capability_policy``）
      由运维在配置页面维护，与具体 deployment 解耦；适合环境性策略
      （例如 sit 环境强制 SUPPRESS 真实集成）。
    - ``system_default_policy``：进程内置硬编码 fallback。

    顺序在前的列表先匹配 → 优先级更高。
    """
    sys_rules = system_default_policy(mode)
    base = (
        list(deployment_rules or [])
        + list(profile_system_rules or [])
        + sys_rules
    )
    new_ctx = _CapCtx(mode=mode, base_rules=base, node_stack=[])
    token = _cap_ctx_var.set(new_ctx)
    try:
        yield
    finally:
        _cap_ctx_var.reset(token)


@contextmanager
def node_capability_scope(
    node_rules: list[CapabilityRule] | None,
) -> Iterator[None]:
    """进入 TaskNode 时压栈节点级覆盖；空 / None 时为 zero-cost no-op。"""
    if not node_rules:
        yield
        return
    cur = _cap_ctx_var.get()
    new_stack = list(cur.node_stack)
    new_stack.append(list(node_rules))
    new_ctx = _CapCtx(mode=cur.mode, base_rules=cur.base_rules, node_stack=new_stack)
    token = _cap_ctx_var.set(new_ctx)
    try:
        yield
    finally:
        _cap_ctx_var.reset(token)


def check_capability(
    builtin_category: str,
    builtin_name: str,
) -> tuple[CapabilityAction, dict[str, Any]]:
    """副作用 builtin 调用入口：返回 (action, redirect_params)。

    查找顺序（高 → 低）：
        node_stack（最近 push 的覆盖优先） → base_rules → ALLOW
    """
    cur = _cap_ctx_var.get()
    # 节点级覆盖：从栈顶向下遍历（最近压栈的优先）
    for rules in reversed(cur.node_stack):
        for r in rules:
            if r.matches(builtin_category, builtin_name):
                return r.action, dict(r.redirect_params)
    for r in cur.base_rules:
        if r.matches(builtin_category, builtin_name):
            return r.action, dict(r.redirect_params)
    # 兜底：未知副作用按 allow，避免阻塞业务（设计文档 §4.1）。
    return CapabilityAction.ALLOW, {}


def get_run_mode() -> RunMode:
    """当前 RunMode，供 persistence / test_runner 等读取。"""
    return _cap_ctx_var.get().mode


def effective_policy_snapshot() -> list[CapabilityRule]:
    """返回当前 (node_stack 自顶向下 ++ base_rules) 合并副本。

    供 :func:`process_starlark_task` 在跨进程边界序列化使用。
    """
    cur = _cap_ctx_var.get()
    out: list[CapabilityRule] = []
    for rules in reversed(cur.node_stack):
        out.extend(r.model_copy() for r in rules)
    out.extend(r.model_copy() for r in cur.base_rules)
    return out
