"""Pydantic V2 models for flow definitions."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from flow_engine.runner.models import CapabilityRule

# 节点 id 的强约束：字母开头，仅允许字母/数字/下划线。
# 作为流程内的逻辑主键使用；name 仅用于可视化展示，不承担任何业务语义。
NODE_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"


class FlowState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"


class NodeState(str, Enum):
    INITIALIZED = "INITIALIZED"
    STAGING = "STAGING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StrategyMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"
    THREAD = "thread"
    PROCESS = "process"


class OnErrorAction(str, Enum):
    RETRY = "retry"
    JUMP = "jump"
    CONTINUE = "continue"
    BREAK = "break"
    IGNORE = "ignore"
    CUSTOM = "custom"


class FlowHooks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on_start: str | None = None
    on_complete: str | None = None
    on_failure: str | None = None


class NodeHooks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_exec: str | None = None
    post_exec: str | None = None


class LoopHooks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_exec: str | None = None
    post_exec: str | None = None
    on_iteration_start: str | None = None
    on_iteration_end: str | None = None


class OnErrorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OnErrorAction | str
    target: str | None = None
    script: str | None = None


class Boundary(BaseModel):
    """Maps context paths (keys) to Starlark names (values) for inputs; reverse for outputs."""

    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)


class ExecutionStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    mode: StrategyMode | str
    concurrency: int = Field(default=4, ge=1)
    timeout: float | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)


class BaseNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    # 节点的逻辑主键。流程内唯一、必填、严格 identifier 形式。
    # 所有引用节点的地方（jumps / parent_map / debug / 运行态指标等）都以 id 为准。
    id: str = Field(
        ...,
        min_length=1,
        pattern=NODE_ID_PATTERN,
        description="节点逻辑主键：字母开头 + 字母/数字/下划线；流程内唯一。",
    )
    # 展示名。Loop/Subflow：留空（"" / 空白）时自动回落到 id。
    # Task：必填非空，流程内唯一（见 FlowDefinition 校验），不参与引擎 id 语义。
    name: str = Field(
        default="",
        description="展示名；Task 必填且在流程内唯一；其它类型留空则回落到 id。",
    )
    strategy_ref: str = "default_sync"
    wait_before: bool = False
    condition: str | None = None
    # 可选说明；不参与调度与执行语义，仅供文档与界面展示。
    description: str | None = None
    on_error: OnErrorConfig | None = None
    hooks: NodeHooks | LoopHooks | None = None

    @model_validator(mode="after")
    def _default_name_to_id(self) -> "BaseNode":
        # Task 的 name 由 TaskNode / FlowDefinition 单独约束，不在此回落到 id。
        if getattr(self, "type", None) == "task":
            return self
        # Loop / Subflow：name 为空时回落到 id，保证展示永远有值。
        if not isinstance(self.name, str) or not self.name.strip():
            object.__setattr__(self, "name", self.id)
        return self


class TaskNode(BaseNode):
    type: Literal["task"] = "task"
    script: str
    boundary: Boundary = Field(default_factory=Boundary)
    # Node 级 CapabilityPolicy 覆盖。优先级高于 deployment_capability_policy
    # 与系统默认；None / 空列表 = 无覆盖。
    # 现有 YAML 不含此字段，反序列化保持 None，向后兼容。
    capability_overrides: list[CapabilityRule] | None = None

    @model_validator(mode="after")
    def _task_requires_display_name(self) -> "TaskNode":
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                "Task node 'name' is required: use a non-empty display name "
                "(unique among all Task nodes in the flow)."
            )
        return self


class IterationCollect(BaseModel):
    """Harvests a value from each iteration's (possibly isolated) context and
    appends it to a list path in the parent context.

    * ``from_path``: path evaluated against the per-iteration context.
    * ``append_to``: path in the PARENT context; if absent or not a list, a
      fresh list is created. The parent list is updated under the parent
      context's lock so concurrent iterations are race-free.
    """

    model_config = ConfigDict(extra="forbid")

    from_path: str
    append_to: str


class LoopNode(BaseNode):
    type: Literal["loop"] = "loop"
    iterable: str
    alias: str
    children: list["FlowMember"] = Field(default_factory=list)
    hooks: LoopHooks | None = None
    # Controls how each loop item is bound into the iteration frame.
    #   "shared" (default): bind the object by reference; mutations inside the
    #                       loop body are visible to later iterations and to
    #                       any sibling references holding the same list.
    #   "shallow": copy.copy() per iteration (top-level isolation only).
    #   "deep":    copy.deepcopy() per iteration (full isolation).
    copy_item: Literal["shared", "shallow", "deep"] = "shared"
    # Controls whether an iteration gets its own isolated ContextStack.
    #   "shared" (default): the iteration body mutates the parent's
    #                       ``$.global`` namespace directly (legacy behaviour).
    #   "fork": each iteration receives a freshly forked ContextStack with a
    #           deep copy of ``global_ns``; writes inside the iteration do not
    #           leak to the parent nor to sibling iterations. Use
    #           ``iteration_collect`` to harvest a per-iteration result.
    iteration_isolation: Literal["shared", "fork"] = "shared"
    # When set, after each iteration completes we read ``from_path`` from the
    # iteration's (possibly isolated) context and append that value to the
    # list at ``append_to`` in the parent context. The parent list grows in
    # iteration-completion order (which, for concurrent loops, is not the same
    # as the source order — pair with a stable key inside the collected value
    # if you need deterministic ordering).
    iteration_collect: IterationCollect | None = None


class SubflowNode(BaseNode):
    type: Literal["subflow"] = "subflow"
    alias: str
    children: list["FlowMember"] = Field(default_factory=list)


FlowMember = Annotated[Union[TaskNode, LoopNode, SubflowNode], Field(discriminator="type")]

TaskNode.model_rebuild()
LoopNode.model_rebuild()
SubflowNode.model_rebuild()


def _migrate_raw_task_display_names(raw_nodes: Any) -> None:
    """In-place: legacy Task dicts with blank ``name`` get ``name`` from ``id``."""

    if not isinstance(raw_nodes, list):
        return

    def walk(children: list[Any]) -> None:
        for item in children:
            if not isinstance(item, dict):
                continue
            t = item.get("type")
            if t == "task":
                nm = item.get("name", "")
                if not (isinstance(nm, str) and nm.strip()):
                    tid = item.get("id", "")
                    item["name"] = str(tid).strip() or "unnamed_task"
            elif t in ("loop", "subflow") and isinstance(item.get("children"), list):
                walk(item["children"])

    walk(raw_nodes)


def _all_tasks_flat(nodes: list[FlowMember]) -> list[TaskNode]:
    out: list[TaskNode] = []

    def walk(m: FlowMember) -> None:
        if isinstance(m, TaskNode):
            out.append(m)
        elif isinstance(m, (LoopNode, SubflowNode)):
            for ch in m.children:
                walk(ch)

    for n in nodes:
        walk(n)
    return out


class FlowDefinition(BaseModel):
    # 注意：允许 extra="ignore" 仅为兼容历史 yaml 中残留的顶层 `name` 字段。
    # `name` 已迁移至 `display_name`；在 `_migrate_name_field` 中会擦除。
    model_config = ConfigDict(extra="ignore")

    # 展示名：允许中文/空格，仅用于 UI；为空时 UI 回落 flow_id。
    # 不参与任何业务逻辑；流程的唯一逻辑主键是目录名 / API 路径上的 `flow_id`。
    display_name: str | None = None
    version: str = "1.0.0"
    strategies: dict[str, ExecutionStrategy]
    nodes: list[FlowMember]
    hooks: FlowHooks | None = None
    initial_context: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_name(cls, data: Any) -> Any:
        """兼容历史 yaml：若只有顶层 ``name`` 而无 ``display_name``，将其迁移为 ``display_name``。

        只处理 mapping 形态的输入；其它类型原样返回，交由后续字段校验报错。
        同时对 ``nodes`` 树内 Task 补全空白 ``name``（回落到 ``id``），以兼容旧定义。
        """
        if not isinstance(data, dict):
            return data
        working = dict(data)
        if isinstance(working.get("nodes"), list):
            _migrate_raw_task_display_names(working["nodes"])
        if "display_name" not in working and "name" in working:
            new_data = dict(working)
            legacy = new_data.pop("name", None)
            if isinstance(legacy, str):
                new_data["display_name"] = legacy
            return new_data
        if "display_name" in working and "name" in working:
            new_data = dict(working)
            new_data.pop("name", None)
            return new_data
        return working

    @model_validator(mode="after")
    def _task_display_names_unique(self) -> "FlowDefinition":
        seen: dict[str, str] = {}
        for t in _all_tasks_flat(self.nodes):
            key = t.name.strip()
            if not key:
                raise ValueError(f"Task node {t.id!r} has an empty display name.")
            if key in seen:
                raise ValueError(
                    f"Duplicate task display name {key!r}: nodes {seen[key]!r} and {t.id!r}."
                )
            seen[key] = t.id
        return self


def iter_member_ids(member: FlowMember) -> list[str]:
    # id 是节点的唯一逻辑主键；不再回落 name。
    out = [member.id]
    if isinstance(member, (LoopNode, SubflowNode)):
        for ch in member.children:
            out.extend(iter_member_ids(ch))
    return out


def collect_all_node_ids(nodes: list[FlowMember]) -> list[str]:
    ids: list[str] = []
    for n in nodes:
        ids.extend(iter_member_ids(n))
    return ids
