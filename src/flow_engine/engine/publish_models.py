"""Pydantic models for multi-version publishing and instance management."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


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
    flow_name: str = ""


class FlowMeta(BaseModel):
    flow_id: str
    latest_version: int = 0
    has_draft: bool = False
    versions: list[FlowVersionMeta] = Field(default_factory=list)
