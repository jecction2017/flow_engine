"""Pydantic schemas for connector configuration in the data dictionary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProtectionSpec(BaseModel):
    max_in_flight: int = Field(default=16, ge=1, le=10_000)
    max_rps: float = Field(default=50.0, ge=0.1, le=100_000.0)
    max_result_docs: int = Field(default=1000, ge=1, le=100_000)
    max_scroll_pages: int = Field(default=10, ge=1, le=1000)
    circuit_failure_threshold: int = Field(default=5, ge=1, le=1000)
    circuit_open_sec: float = Field(default=30.0, ge=1.0, le=3600.0)


class AuthSpec(BaseModel):
    type: Literal["none", "basic", "api_key", "bearer", "certificate"] = "none"
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    bearer_token: str | None = None
    client_cert: str | None = None
    client_key: str | None = None
    ca_certs: str | None = None


class ElasticsearchInstanceSpec(BaseModel):
    hosts: list[str] = Field(min_length=1)
    verify_certs: bool = True
    auth: AuthSpec = Field(default_factory=AuthSpec)
    allowed_index_patterns: list[str] | None = None
    request_timeout_sec: float | None = None
    protection: ProtectionSpec | None = None


class ElasticsearchDefaults(BaseModel):
    request_timeout_sec: float = Field(default=30.0, ge=1.0, le=600.0)
    protection: ProtectionSpec = Field(default_factory=ProtectionSpec)


class ElasticsearchConfig(BaseModel):
    defaults: ElasticsearchDefaults = Field(default_factory=ElasticsearchDefaults)
    instances: dict[str, ElasticsearchInstanceSpec] = Field(default_factory=dict)

    @field_validator("instances")
    @classmethod
    def _non_empty_ids(cls, v: dict[str, ElasticsearchInstanceSpec]) -> dict[str, ElasticsearchInstanceSpec]:
        for key in v:
            if not key.strip():
                raise ValueError("instance id must be non-empty")
        return v


def parse_elasticsearch_config(raw: Any) -> ElasticsearchConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    return ElasticsearchConfig.model_validate(raw)
