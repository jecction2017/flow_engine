"""Pydantic schemas for connector configuration in the data dictionary."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProtectionSpec(BaseModel):
    """连接器实例的自我保护参数（并发 / 限流 / 熔断 / 结果规模）。

    在 ``ProtectionPipeline`` 中按实例生效；``defaults.protection`` 可被各实例
    ``protection`` 字段覆盖合并。策略校验类错误（``ConnectorError``）不计入熔断失败次数。
    """

    max_in_flight: int = Field(
        default=16,
        ge=1,
        le=10_000,
        description=(
            "同一实例上允许同时进行的出站请求数上限（并发闸门）。"
            "超出时立即拒绝，错误为 CONNECTOR_CONCURRENCY_LIMIT。"
        ),
    )
    max_rps: float = Field(
        default=50.0,
        ge=0.1,
        le=100_000.0,
        description=(
            "每秒允许发起的请求数上限（令牌桶限流）。"
            "超出时拒绝，错误为 CONNECTOR_RATE_LIMIT。"
        ),
    )
    max_result_docs: int = Field(
        default=1000,
        ge=1,
        le=100_000,
        description=(
            "单次调用返回的最大条数上限。"
            "Elasticsearch search 的 size、Kafka consume 的 max_records 等会被钳制到此值；"
            "未指定 size 时默认取本值。"
        ),
    )
    max_scroll_pages: int = Field(
        default=10,
        ge=1,
        le=1000,
        description=(
            "Elasticsearch scroll 允许翻页的最大页数；"
            "每页条数仍受 max_result_docs 限制。仅 scroll 类操作使用。"
        ),
    )
    circuit_failure_threshold: int = Field(
        default=5,
        ge=1,
        le=1000,
        description=(
            "熔断器打开前累计的失败次数阈值。"
            "仅统计传输/超时等异常；ConnectorError（如索引不允许）不计入。"
            "达到后该实例在 circuit_open_sec 内拒绝一切请求（CIRCUIT_OPEN）。"
        ),
    )
    circuit_open_sec: float = Field(
        default=30.0,
        ge=1.0,
        le=3600.0,
        description="熔断打开后拒绝请求的持续时间（秒）；到期后允许试探性调用，成功则关闭熔断。",
    )


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
