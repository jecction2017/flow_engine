"""Pydantic V2 models for flow definitions."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


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
    name: str
    id: str | None = Field(default=None, description="Optional explicit id; defaults to name")
    strategy_ref: str = "default_sync"
    wait_before: bool = False
    condition: str | None = None
    on_error: OnErrorConfig | None = None
    hooks: NodeHooks | LoopHooks | None = None


class TaskNode(BaseNode):
    type: Literal["task"] = "task"
    script: str
    boundary: Boundary = Field(default_factory=Boundary)


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


class SubflowNode(BaseNode):
    type: Literal["subflow"] = "subflow"
    alias: str
    children: list["FlowMember"] = Field(default_factory=list)


FlowMember = Annotated[Union[TaskNode, LoopNode, SubflowNode], Field(discriminator="type")]

TaskNode.model_rebuild()
LoopNode.model_rebuild()
SubflowNode.model_rebuild()


class FlowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str = "1.0.0"
    strategies: dict[str, ExecutionStrategy]
    nodes: list[FlowMember]
    hooks: FlowHooks | None = None
    initial_context: dict[str, Any] | None = None


def iter_member_ids(member: FlowMember) -> list[str]:
    nid = member.id or member.name
    out = [nid]
    if isinstance(member, (LoopNode, SubflowNode)):
        for ch in member.children:
            out.extend(iter_member_ids(ch))
    return out


def collect_all_node_ids(nodes: list[FlowMember]) -> list[str]:
    ids: list[str] = []
    for n in nodes:
        ids.extend(iter_member_ids(n))
    return ids
