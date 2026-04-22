"""Pydantic models for multi-version publishing and instance management."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PublishStatus(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHING = "publishing"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class ChannelState(BaseModel):
    version: int | None = None
    status: PublishStatus = PublishStatus.UNPUBLISHED
    published_at: float | None = None
    stopped_at: float | None = None


class FlowPublishState(BaseModel):
    flow_id: str
    production: ChannelState = Field(default_factory=ChannelState)
    gray: ChannelState = Field(default_factory=ChannelState)


class FlowInstance(BaseModel):
    instance_id: str
    flow_id: str
    version: int
    channel: str
    started_at: float
    last_heartbeat: float
    status: Literal["running", "stopped", "failed"] = "running"
    pid: int | None = None
    host: str | None = None


class FlowVersionMeta(BaseModel):
    version: int
    created_at: float
    description: str | None = None
    # 提交版本时的展示名快照。历史 meta.json 里叫 ``flow_name``，
    # 下方 validator 会兼容迁移。
    display_name: str = ""

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_flow_name(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "display_name" not in data and "flow_name" in data:
                new_data = dict(data)
                legacy = new_data.pop("flow_name", None)
                if isinstance(legacy, str):
                    new_data["display_name"] = legacy
                return new_data
            if "display_name" in data and "flow_name" in data:
                new_data = dict(data)
                new_data.pop("flow_name", None)
                return new_data
        return data


class FlowMeta(BaseModel):
    flow_id: str
    latest_version: int = 0
    has_draft: bool = False
    versions: list[FlowVersionMeta] = Field(default_factory=list)
