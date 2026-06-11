"""Typed models for generic metric and feature computation."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricOperation(str, Enum):
    COUNT = "count"
    DISTINCT_COUNT = "distinct_count"
    SUM = "sum"
    AVG = "avg"
    MAX = "max"
    MIN = "min"
    RATIO = "ratio"
    TOPK = "topk"
    ENTROPY = "entropy"
    PERCENTILE = "percentile"
    FREQ_MAP_COUNT = "freq_map_count"
    CO_OCCUR = "co_occur"


class PipelineStage(str, Enum):
    FETCH = "fetch"
    NORMALIZE = "normalize"
    ENRICH = "enrich"
    METRIC = "metric"
    FEATURE = "feature"
    RULE = "rule"
    RENDER = "render"


class DataSet(BaseModel):
    """Generic row-oriented dataset for metric computation."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = "generic_rows"
    rows: list[dict[str, Any]] = Field(default_factory=list)
    timestamp_field: str | None = "ts"
    window_start_ts: int | float | None = None
    window_end_ts: int | float | None = None
    weight_field: str = "count"


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    op: MetricOperation
    field: str | None = None
    numerator: str | None = None
    denominator: str | None = None
    where: dict[str, Any] = Field(default_factory=dict)
    percentile: float | None = Field(default=None, ge=0, le=100)
    k: int = Field(default=3, ge=1)
    values: list[Any] = Field(default_factory=list)
    map_keys: list[str] = Field(default_factory=list)


class MetricPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = "default_metric_plan"
    dataset_id: str = "generic_rows"
    group_by: list[str] = Field(default_factory=list)
    metrics: list[MetricDefinition] = Field(default_factory=list)


class FeatureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expression: str


class FeaturePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = "default_feature_plan"
    features: list[FeatureDefinition] = Field(default_factory=list)


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_schema_version: str = "v1"
    feature_set_id: str = "default"
    group_key: dict[str, Any]
    metrics: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)


class RuleClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: str
    value: Any


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str = ""
    enabled: bool = True
    severity: str = "medium"
    score: float = 1.0
    all: list[RuleClause] = Field(default_factory=list)
    any: list[RuleClause] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RuleMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    severity: str
    score: float
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PipelineContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = "default"
    rule_set_id: str = "default"
    feature_schema_version: str = "v1"
    tags: dict[str, Any] = Field(default_factory=dict)


class PipelineOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_schema_version: str
    feature_set_id: str
    snapshots: list[FeatureSnapshot] = Field(default_factory=list)
    matches: list[RuleMatch] = Field(default_factory=list)


class StageContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PipelineStage
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class PipelineContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: str = "metric_feature_pipeline_contract_v1"
    stages: list[StageContract] = Field(default_factory=list)


def default_pipeline_contract() -> PipelineContract:
    return PipelineContract(
        stages=[
            StageContract(
                stage=PipelineStage.FETCH,
                description="Read raw events from external source.",
                input_schema={"source": "connector/query config"},
                output_schema={"records": "list[dict]"},
            ),
            StageContract(
                stage=PipelineStage.NORMALIZE,
                description="Convert raw records to canonical DataSet rows.",
                input_schema={"records": "list[dict]"},
                output_schema={"dataset": "DataSet"},
            ),
            StageContract(
                stage=PipelineStage.ENRICH,
                description="Join side-input baseline dictionaries into rows.",
                input_schema={"dataset": "DataSet", "side_input": "list[dict] or dict"},
                output_schema={"dataset": "DataSet"},
            ),
            StageContract(
                stage=PipelineStage.METRIC,
                description="Aggregate group-level metrics by MetricPlan.",
                input_schema={"dataset": "DataSet", "metric_plan": "MetricPlan"},
                output_schema={"snapshots.metrics": "dict"},
            ),
            StageContract(
                stage=PipelineStage.FEATURE,
                description="Derive features from metrics by FeaturePlan.",
                input_schema={"snapshots.metrics": "dict", "feature_plan": "FeaturePlan"},
                output_schema={"snapshots.features": "dict"},
            ),
            StageContract(
                stage=PipelineStage.RULE,
                description="Evaluate rules and emit structured matches.",
                input_schema={"snapshots": "list[FeatureSnapshot]", "rules": "list[RuleDefinition]"},
                output_schema={"matches": "list[RuleMatch]"},
            ),
            StageContract(
                stage=PipelineStage.RENDER,
                description="Optional business-specific output rendering outside core.",
                input_schema={"matches": "list[RuleMatch]", "snapshots": "list[FeatureSnapshot]"},
                output_schema={"output": "business-defined"},
            ),
        ]
    )
