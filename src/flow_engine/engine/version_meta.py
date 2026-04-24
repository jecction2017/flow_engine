"""Pydantic models for per-flow version index metadata (meta.json)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class FlowVersionMeta(BaseModel):
    version: int
    created_at: float
    description: str | None = None
    # Snapshot display name at commit time; legacy meta.json used ``flow_name``.
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
