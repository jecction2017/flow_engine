"""Starlark builtins for generic metric-feature pipelines."""

from __future__ import annotations

from typing import Any

from flow_engine.metric_feature.models import (
    FeaturePlan,
    FeatureSnapshot,
    MetricPlan,
    PipelineContext,
    RuleDefinition,
)
from flow_engine.metric_feature.service import (
    compute_features,
    dataset_from_raw,
    enrich_dataset_with_side_input,
    evaluate_rules,
    load_feature_plan_from_dict,
    load_metric_plan_from_dict,
    load_rules_from_dict,
    load_scenario_config_from_dict,
    pipeline_contract,
    run_pipeline_from_dict_name,
    run_pipeline,
)
from flow_engine.starlark_sdk.builtin_registry import BuiltinArgSpec, PythonBuiltinSpec, register_builtin

_SUPPRESSED: dict[str, Any] = {"_suppressed": True, "ok": False, "reason": "integration suppressed"}


def _metric_plan_from_raw(raw: dict[str, Any] | None, *, dictionary_name: str = "default") -> MetricPlan:
    if not raw:
        return load_metric_plan_from_dict(dictionary_name)
    return MetricPlan.model_validate(raw)


def _feature_plan_from_raw(raw: dict[str, Any] | None, *, dictionary_name: str = "default") -> FeaturePlan | None:
    if raw is None:
        return load_feature_plan_from_dict(dictionary_name)
    return FeaturePlan.model_validate(raw)


def _rules_from_raw(raw: list[dict[str, Any]] | None, *, dictionary_name: str = "default") -> list[RuleDefinition]:
    if raw is None:
        return load_rules_from_dict(dictionary_name)
    return [RuleDefinition.model_validate(item) for item in raw]


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/compute",
        starlark_name="metric_feature_compute",
        category="integration",
        summary="对任意行数据计算指标与特征（DataSet->Metric->Feature）",
        signature=(
            BuiltinArgSpec(name="dataset", type="dict"),
            BuiltinArgSpec(name="metric_plan", type="dict", required=False),
            BuiltinArgSpec(name="feature_plan", type="dict", required=False),
            BuiltinArgSpec(name="dictionary_name", type="str", required=False),
            BuiltinArgSpec(name="context", type="dict", required=False),
        ),
        returns="dict",
        side_effects="none",
        suppress_result=_SUPPRESSED,
    )
)
def metric_feature_compute(
    dataset: dict[str, Any],
    metric_plan: dict[str, Any] | None = None,
    feature_plan: dict[str, Any] | None = None,
    dictionary_name: str = "default",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ds = dataset_from_raw(dataset)
    mp = _metric_plan_from_raw(metric_plan, dictionary_name=dictionary_name)
    fp = _feature_plan_from_raw(feature_plan, dictionary_name=dictionary_name)
    ctx = PipelineContext.model_validate(context) if context else PipelineContext()
    snapshots = compute_features(ds, mp, fp, context=ctx)
    return {"snapshots": [snapshot.model_dump() for snapshot in snapshots]}


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/evaluate_rules",
        starlark_name="metric_feature_rule_eval",
        category="integration",
        summary="对特征快照执行规则DSL并返回命中",
        signature=(
            BuiltinArgSpec(name="snapshots", type="list"),
            BuiltinArgSpec(name="rules", type="list", required=False),
        ),
        returns="dict",
        side_effects="none",
        suppress_result=_SUPPRESSED,
    )
)
def metric_feature_rule_eval(
    snapshots: list[dict[str, Any]],
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot_models = [FeatureSnapshot.model_validate(item) for item in (snapshots or []) if isinstance(item, dict)]
    rule_models = _rules_from_raw(rules)
    matches = evaluate_rules(snapshot_models, rule_models)
    return {"matches": [match.model_dump() for match in matches]}


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/pipeline",
        starlark_name="metric_feature_pipeline",
        category="integration",
        summary="一体化计算指标特征并执行规则",
        signature=(
            BuiltinArgSpec(name="dataset", type="dict"),
            BuiltinArgSpec(name="metric_plan", type="dict", required=False),
            BuiltinArgSpec(name="feature_plan", type="dict", required=False),
            BuiltinArgSpec(name="rules", type="list", required=False),
            BuiltinArgSpec(name="dictionary_name", type="str", required=False),
            BuiltinArgSpec(name="context", type="dict", required=False),
        ),
        returns="dict",
        side_effects="none",
        suppress_result=_SUPPRESSED,
    )
)
def metric_feature_pipeline(
    dataset: dict[str, Any],
    metric_plan: dict[str, Any] | None = None,
    feature_plan: dict[str, Any] | None = None,
    rules: list[dict[str, Any]] | None = None,
    dictionary_name: str = "default",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ds = dataset_from_raw(dataset)
    if metric_plan is None and feature_plan is None and rules is None:
        ctx = PipelineContext.model_validate(context) if context else None
        out = run_pipeline_from_dict_name(ds, dictionary_name=dictionary_name, context=ctx)
    else:
        mp = _metric_plan_from_raw(metric_plan, dictionary_name=dictionary_name)
        fp = _feature_plan_from_raw(feature_plan, dictionary_name=dictionary_name)
        rs = _rules_from_raw(rules, dictionary_name=dictionary_name)
        ctx = PipelineContext.model_validate(context) if context else PipelineContext()
        out = run_pipeline(ds, mp, fp, rs, context=ctx)
    return out.model_dump()


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/load_metric_plan",
        starlark_name="metric_feature_load_metric_plan",
        category="dictionary",
        summary="从数据字典按场景载入 Metric DSL",
        signature=(BuiltinArgSpec(name="dictionary_name", type="str", required=False),),
        returns="dict",
        side_effects="disk",
    )
)
def metric_feature_load_metric_plan(dictionary_name: str = "default") -> dict[str, Any]:
    return load_metric_plan_from_dict(dictionary_name).model_dump()


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/load_feature_plan",
        starlark_name="metric_feature_load_feature_plan",
        category="dictionary",
        summary="从数据字典按场景载入 Feature DSL",
        signature=(BuiltinArgSpec(name="dictionary_name", type="str", required=False),),
        returns="dict",
        side_effects="disk",
    )
)
def metric_feature_load_feature_plan(dictionary_name: str = "default") -> dict[str, Any]:
    return load_feature_plan_from_dict(dictionary_name).model_dump()


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/load_rules",
        starlark_name="metric_feature_load_rules",
        category="dictionary",
        summary="从数据字典按场景载入 Rule DSL",
        signature=(BuiltinArgSpec(name="dictionary_name", type="str", required=False),),
        returns="list",
        side_effects="disk",
    )
)
def metric_feature_load_rules(dictionary_name: str = "default") -> list[dict[str, Any]]:
    return [rule.model_dump() for rule in load_rules_from_dict(dictionary_name)]


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/load_scenario",
        starlark_name="metric_feature_load_scenario",
        category="dictionary",
        summary="按字典名载入完整特征场景配置",
        signature=(BuiltinArgSpec(name="dictionary_name", type="str", required=False),),
        returns="dict",
        side_effects="none",
    )
)
def metric_feature_load_scenario(dictionary_name: str = "default") -> dict[str, Any]:
    return load_scenario_config_from_dict(dictionary_name)


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/pipeline_contract",
        starlark_name="metric_feature_pipeline_contract",
        category="system",
        summary="返回通用6阶段数据处理契约",
        returns="dict",
        side_effects="none",
    )
)
def metric_feature_pipeline_contract() -> dict[str, Any]:
    return pipeline_contract().model_dump()


@register_builtin(
    PythonBuiltinSpec(
        id="python://metric_feature/enrich_dataset",
        starlark_name="metric_feature_enrich_dataset",
        category="runtime",
        summary="按 key 将 side_input 关联进 DataSet.rows",
        signature=(
            BuiltinArgSpec(name="dataset", type="dict"),
            BuiltinArgSpec(name="side_rows", type="list"),
            BuiltinArgSpec(name="key_fields", type="list"),
            BuiltinArgSpec(name="include_fields", type="list", required=False),
            BuiltinArgSpec(name="prefix", type="str", required=False),
            BuiltinArgSpec(name="overwrite", type="any", required=False),
        ),
        returns="dict",
        side_effects="none",
        suppress_result=_SUPPRESSED,
    )
)
def metric_feature_enrich_dataset(
    dataset: dict[str, Any],
    side_rows: list[dict[str, Any]],
    key_fields: list[str],
    include_fields: list[str] | None = None,
    prefix: str = "",
    overwrite: bool = True,
) -> dict[str, Any]:
    ds = dataset_from_raw(dataset)
    enriched = enrich_dataset_with_side_input(
        ds,
        [row for row in side_rows if isinstance(row, dict)],
        key_fields=[str(item) for item in key_fields if str(item)],
        include_fields=[str(item) for item in include_fields] if include_fields is not None else None,
        prefix=prefix,
        overwrite=overwrite,
    )
    return enriched.model_dump()
