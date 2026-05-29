"""Pydantic schemas for HTTP connector configuration in the data dictionary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from flow_engine.connectors.config import ProtectionSpec


class HttpBaseSpec(BaseModel):
    request_timeout_sec: float = Field(default=30.0, ge=0.1, le=600.0)
    verify_ssl: bool = True
    retries: int = Field(default=0, ge=0, le=10)
    retry_backoff_sec: float = Field(default=0.2, ge=0.0, le=30.0)
    default_headers: dict[str, str] = Field(default_factory=dict)


class HttpEndpointSpec(BaseModel):
    path: str = Field(..., min_length=1)
    method: str = Field(default="GET", min_length=1)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    query_defaults: dict[str, str] = Field(default_factory=dict)
    request_timeout_sec: float | None = Field(default=None, ge=0.1, le=600.0)
    auth_provider: str | None = None

    @field_validator("method")
    @classmethod
    def _upper_method(cls, value: str) -> str:
        return value.strip().upper()


class HttpServiceSpec(BaseModel):
    base_url: str = Field(..., min_length=1)
    common_headers: dict[str, str] = Field(default_factory=dict)
    request_timeout_sec: float | None = Field(default=None, ge=0.1, le=600.0)
    auth_provider: str | None = None
    endpoints: dict[str, HttpEndpointSpec] = Field(default_factory=dict)

    @field_validator("endpoints")
    @classmethod
    def _validate_endpoints(cls, value: dict[str, HttpEndpointSpec]) -> dict[str, HttpEndpointSpec]:
        for endpoint_name in value:
            if not endpoint_name.strip():
                raise ValueError("endpoint name must be non-empty")
        return value


class HttpAuthProviderSpec(BaseModel):
    type: Literal["none", "iam", "soa", "apig"] = "none"
    token_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scope: str | None = None
    audience: str | None = None
    header_name: str = "Authorization"
    token_prefix: str = "Bearer"
    ttl_sec: int = Field(default=3600, ge=60, le=86400)
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_required_fields(self) -> HttpAuthProviderSpec:
        if self.type == "iam":
            if not self.token_url:
                raise ValueError("auth provider (iam) requires token_url")
            if not self.client_id:
                raise ValueError("auth provider (iam) requires client_id")
            if not self.client_secret:
                raise ValueError("auth provider (iam) requires client_secret")
        return self


class HttpInstanceSpec(BaseModel):
    base: HttpBaseSpec = Field(default_factory=HttpBaseSpec)
    protection: ProtectionSpec | None = None
    services: dict[str, HttpServiceSpec] = Field(default_factory=dict)
    auth_providers: dict[str, HttpAuthProviderSpec] = Field(default_factory=dict)

    @field_validator("services")
    @classmethod
    def _validate_services(cls, value: dict[str, HttpServiceSpec]) -> dict[str, HttpServiceSpec]:
        for service_name in value:
            if not service_name.strip():
                raise ValueError("service name must be non-empty")
        return value


class HttpDefaults(BaseModel):
    protection: ProtectionSpec = Field(default_factory=ProtectionSpec)


class HttpConfig(BaseModel):
    defaults: HttpDefaults = Field(default_factory=HttpDefaults)
    instances: dict[str, HttpInstanceSpec] = Field(default_factory=dict)

    @field_validator("instances")
    @classmethod
    def _non_empty_ids(cls, value: dict[str, HttpInstanceSpec]) -> dict[str, HttpInstanceSpec]:
        for key in value:
            if not key.strip():
                raise ValueError("instance id must be non-empty")
        return value


def parse_http_config(raw: Any) -> HttpConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    return HttpConfig.model_validate(raw)
