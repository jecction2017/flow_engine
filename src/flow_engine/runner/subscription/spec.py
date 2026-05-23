"""Pydantic models for subscription schedule_config."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# context_mapping modes align with Test Center (see runner/context_mapping.py):
# spread | wrap | rules


class SubscriptionSection(BaseModel):
    """References a data-dictionary Kafka consumer (cluster.topic.consumer)."""

    consumer_id: str = Field(..., min_length=1)
    producer_id: str | None = Field(
        default=None,
        description="Optional default producer for DLQ on this subscription.",
    )
    partitions: list[int] | None = None
    start_position: str | dict[str, Any] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class ConsumptionSection(BaseModel):
    batch_max_records: int = Field(default=100, ge=1, le=10_000)
    poll_timeout_ms: int = Field(default=1000, ge=100, le=60_000)
    commit_policy: Literal["on_success"] = "on_success"
    max_retries: int = Field(default=3, ge=0, le=100)
    retry_backoff_ms: int = Field(default=1000, ge=0)
    dlq: dict[str, Any] | None = None
    idempotency: dict[str, Any] | None = None


class DispatchSection(BaseModel):
    max_in_flight: int = Field(default=8, ge=1, le=500)
    run_timeout_s: int | None = Field(default=None, ge=1)


class ParseSection(BaseModel):
    """How to decode the message and map it into flow ``global_ns`` (user-defined)."""

    codec: Literal["json"] = Field(
        default="json",
        description="Message body codec; v1 only supports UTF-8 JSON object/array.",
    )
    transform: Literal["mapping", "script"] = Field(
        default="mapping",
        description="mapping: Test Center context_mapping; script: Starlark returning a dict.",
    )
    mapping: dict[str, Any] | None = Field(
        default=None,
        description="When transform=mapping: spread | wrap | rules. None = spread as-is.",
    )
    script: str | None = Field(
        default=None,
        description="When transform=script: Starlark; global ``payload`` = decoded JSON.",
    )

    @model_validator(mode="after")
    def _validate_transform(self) -> ParseSection:
        if self.transform == "script" and not (self.script and str(self.script).strip()):
            raise ValueError("parse.script is required when parse.transform is 'script'")
        return self


class IngressPolicySection(BaseModel):
    max_restarts: int = Field(default=3, ge=0)
    restart_backoff_s: int = Field(default=15, ge=1)


def ingress_restart_delay_s(backoff_base: int, attempt: int) -> float:
    """Seconds to wait before retry ``attempt`` (1-indexed). Exponential: base * 2^(attempt-1)."""
    if attempt < 1:
        return float(backoff_base)
    return float(backoff_base * (2 ** (attempt - 1)))


class SubscriptionSpec(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    subscription: SubscriptionSection
    consumption: ConsumptionSection = Field(default_factory=ConsumptionSection)
    dispatch: DispatchSection = Field(default_factory=DispatchSection)
    parse: ParseSection = Field(default_factory=ParseSection)
    ingress_policy: IngressPolicySection = Field(default_factory=IngressPolicySection)


def load_subscription_spec(raw: dict[str, Any] | None) -> SubscriptionSpec:
    if not raw:
        raise ValueError("subscription deployment requires schedule_config")
    return SubscriptionSpec.model_validate(raw)
