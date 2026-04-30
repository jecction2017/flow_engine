"""Runtime layer models: RunMode / RunOptions / MockConfig / CapabilityRule.

These types are intentionally **independent of `flow_engine.engine.*`** so that
``engine.models`` can import :class:`CapabilityRule` without creating an import
cycle, and so that subprocess workers (`process_starlark_task`) can deserialize
them without dragging in heavy orchestrator code.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunMode(str, Enum):
    """运行模式 — 影响默认 CapabilityPolicy 与持久化策略。"""

    DEBUG = "debug"
    SHADOW = "shadow"
    PRODUCTION = "production"


class CapabilityAction(str, Enum):
    """对副作用 builtin 调用的处置动作。"""

    ALLOW = "allow"
    SUPPRESS = "suppress"
    REDIRECT = "redirect"


class CapabilityRule(BaseModel):
    """单条能力规则。匹配优先级：``builtin_name`` > ``builtin_category`` > 通配。"""

    model_config = ConfigDict(extra="forbid")

    builtin_category: str | None = None
    builtin_name: str | None = None
    action: CapabilityAction
    redirect_params: dict[str, Any] = Field(default_factory=dict)

    def matches(self, builtin_category: str, builtin_name: str) -> bool:
        """命中判定。返回 ``True`` 表示命中本规则。

        语义与设计文档 4.1 一致：
        1) ``builtin_name`` 不为 None → 必须与传入 builtin_name 完全相等。
        2) 否则 ``builtin_category`` 不为 None → 必须与传入 category 完全相等。
        3) 否则（两者均为 None）→ 通配命中。
        """
        if self.builtin_name is not None:
            return self.builtin_name == builtin_name
        if self.builtin_category is not None:
            return self.builtin_category == builtin_category
        return True


class MockMode(str, Enum):
    SCRIPT = "script"
    FIXED = "fixed"
    RECORD_REPLAY = "record_replay"
    FAULT = "fault"


class FaultType(str, Enum):
    TIMEOUT = "timeout"
    EXCEPTION = "exception"
    DIRTY_DATA = "dirty_data"


class MockConfig(BaseModel):
    """节点级 Mock 配置。同一时刻仅一种模式生效；字段约束由 validator 强制。"""

    model_config = ConfigDict(extra="forbid")

    mode: MockMode

    # script 模式
    script: str | None = None

    # fixed 模式
    result: dict[str, Any] | None = None

    # record_replay 模式
    lookup_ns: str | None = None
    profile_code: str | None = None
    key_expr: str | None = None
    record_on_miss: bool = True

    # fault 模式
    fault_type: FaultType | None = None
    fault_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_fields(self) -> "MockConfig":
        if self.mode == MockMode.SCRIPT and not self.script:
            raise ValueError("script mode requires `script`")
        if self.mode == MockMode.FIXED and self.result is None:
            raise ValueError("fixed mode requires `result`")
        if self.mode == MockMode.RECORD_REPLAY and not self.lookup_ns:
            raise ValueError("record_replay mode requires `lookup_ns`")
        if self.mode == MockMode.FAULT and not self.fault_type:
            raise ValueError("fault mode requires `fault_type`")
        return self


class RunOptions(BaseModel):
    """单次 ``FlowRuntime.run()`` 的运行选项。"""

    model_config = ConfigDict(extra="forbid")

    mode: RunMode = RunMode.PRODUCTION
    mock_overrides: dict[str, MockConfig] = Field(default_factory=dict)
    deployment_capability_policy: list[CapabilityRule] = Field(default_factory=list)
