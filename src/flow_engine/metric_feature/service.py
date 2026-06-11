"""Service layer for generic metric-feature pipelines."""

from __future__ import annotations

import copy
from typing import Any

from flow_engine.metric_feature.dsl import feature_plan_from_rows, metric_plan_from_rows, rules_from_rows
from flow_engine.metric_feature.engine import compute_snapshots
from flow_engine.metric_feature.models import (
    DataSet,
    FeaturePlan,
    FeatureSnapshot,
    MetricPlan,
    PipelineContract,
    PipelineContext,
    PipelineOutput,
    RuleClause,
    RuleDefinition,
    RuleMatch,
    default_pipeline_contract,
)
from flow_engine.stores.data_dict import lookup as dict_get


def compute_features(
    dataset: DataSet,
    metric_plan: MetricPlan,
    feature_plan: FeaturePlan | None = None,
    *,
    context: PipelineContext | None = None,
) -> list[FeatureSnapshot]:
    schema_version = context.feature_schema_version if context else "v1"
    feature_set_id = context.rule_set_id if context else "default"
    return compute_snapshots(
        dataset,
        metric_plan,
        feature_plan,
        feature_schema_version=schema_version,
        feature_set_id=feature_set_id,
    )


def evaluate_rules(
    snapshots: list[FeatureSnapshot],
    rules: list[RuleDefinition],
) -> list[RuleMatch]:
    matches: list[RuleMatch] = []
    for snapshot in snapshots:
        bag = dict(snapshot.metrics)
        bag.update(snapshot.features)
        for rule in rules:
            if not rule.enabled:
                continue
            all_ok = all(_check_clause(clause, bag) for clause in rule.all)
            any_ok = True if not rule.any else any(_check_clause(clause, bag) for clause in rule.any)
            if all_ok and any_ok:
                evidence: dict[str, Any] = {clause.field: bag.get(clause.field) for clause in list(rule.all) + list(rule.any)}
                evidence["group_key"] = snapshot.group_key
                matches.append(
                    RuleMatch(
                        rule_id=rule.rule_id,
                        severity=rule.severity,
                        score=rule.score,
                        description=rule.description,
                        tags=rule.tags,
                        evidence=evidence,
                    )
                )
    return matches


def run_pipeline(
    dataset: DataSet,
    metric_plan: MetricPlan,
    feature_plan: FeaturePlan | None = None,
    rules: list[RuleDefinition] | None = None,
    *,
    context: PipelineContext | None = None,
    optimize_dataset: bool | str = "auto",
) -> PipelineOutput:
    source_dataset = _select_dataset_for_compute(dataset, metric_plan, optimize_dataset=optimize_dataset)
    snapshots = compute_features(source_dataset, metric_plan, feature_plan, context=context)
    matches = evaluate_rules(snapshots, rules or [])
    schema_version = context.feature_schema_version if context else "v1"
    feature_set_id = context.rule_set_id if context else "default"
    return PipelineOutput(
        feature_schema_version=schema_version,
        feature_set_id=feature_set_id,
        snapshots=snapshots,
        matches=matches,
    )


def load_metric_plan_from_dict(
    dictionary_name: str = "default",
    *,
    root_path: str = "metric_feature.scenarios",
    default_group_by: list[str] | None = None,
) -> MetricPlan:
    config = load_scenario_config_from_dict(dictionary_name, root_path=root_path)
    rows = _extract_rows(config.get("metric_dsl"))
    effective_group_by = default_group_by
    if effective_group_by is None and isinstance(config.get("default_group_by"), list):
        effective_group_by = [str(item) for item in config["default_group_by"] if str(item)]
    return metric_plan_from_rows(
        rows,
        plan_id=f"{dictionary_name}_metric_plan",
        default_group_by=effective_group_by,
    )


def load_feature_plan_from_dict(
    dictionary_name: str = "default",
    *,
    root_path: str = "metric_feature.scenarios",
) -> FeaturePlan:
    config = load_scenario_config_from_dict(dictionary_name, root_path=root_path)
    rows = _extract_rows(config.get("feature_dsl"))
    return feature_plan_from_rows(rows, plan_id=f"{dictionary_name}_feature_plan")


def load_rules_from_dict(
    dictionary_name: str = "default",
    *,
    root_path: str = "metric_feature.scenarios",
) -> list[RuleDefinition]:
    config = load_scenario_config_from_dict(dictionary_name, root_path=root_path)
    rows = _extract_rows(config.get("rule_dsl"))
    return rules_from_rows(rows)


def dataset_from_raw(raw: dict[str, Any]) -> DataSet:
    return DataSet.model_validate(raw)


def pipeline_contract() -> PipelineContract:
    return default_pipeline_contract()


def enrich_dataset_with_side_input(
    dataset: DataSet,
    side_rows: list[dict[str, Any]],
    *,
    key_fields: list[str],
    include_fields: list[str] | None = None,
    prefix: str = "",
    overwrite: bool = True,
) -> DataSet:
    if not key_fields:
        return dataset.model_copy(deep=True)
    mapping: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in side_rows:
        if not isinstance(row, dict):
            continue
        key = tuple(row.get(field) for field in key_fields)
        mapping[key] = row
    out_rows: list[dict[str, Any]] = []
    for row in dataset.rows:
        if not isinstance(row, dict):
            continue
        joined = copy.deepcopy(row)
        key = tuple(row.get(field) for field in key_fields)
        side = mapping.get(key)
        if side:
            for k, v in side.items():
                if k in key_fields:
                    continue
                if include_fields is not None and k not in include_fields:
                    continue
                target_key = f"{prefix}{k}" if prefix else k
                if not overwrite and target_key in joined:
                    continue
                joined[target_key] = copy.deepcopy(v)
        out_rows.append(joined)
    return DataSet(
        dataset_id=dataset.dataset_id,
        rows=out_rows,
        timestamp_field=dataset.timestamp_field,
        window_start_ts=dataset.window_start_ts,
        window_end_ts=dataset.window_end_ts,
        weight_field=dataset.weight_field,
    )


def load_scenario_config_from_dict(
    dictionary_name: str = "default",
    *,
    root_path: str = "metric_feature.scenarios",
) -> dict[str, Any]:
    # preferred path: metric_feature.scenarios.<dictionary_name>
    candidates = [f"{root_path}.{dictionary_name}", dictionary_name]
    for path in candidates:
        if not path:
            continue
        raw = dict_get(path, None)
        if isinstance(raw, dict):
            return raw
    return {}


def run_pipeline_from_dict_name(
    dataset: DataSet,
    dictionary_name: str = "default",
    *,
    context: PipelineContext | None = None,
    root_path: str = "metric_feature.scenarios",
) -> PipelineOutput:
    metric_plan = load_metric_plan_from_dict(dictionary_name, root_path=root_path)
    feature_plan = load_feature_plan_from_dict(dictionary_name, root_path=root_path)
    rules = load_rules_from_dict(dictionary_name, root_path=root_path)
    resolved_context = context
    if resolved_context is None:
        scenario = load_scenario_config_from_dict(dictionary_name, root_path=root_path)
        raw_context = scenario.get("context")
        if isinstance(raw_context, dict):
            resolved_context = PipelineContext.model_validate(raw_context)
    if resolved_context is None:
        resolved_context = PipelineContext(rule_set_id=dictionary_name)
    return run_pipeline(dataset, metric_plan, feature_plan, rules, context=resolved_context, optimize_dataset="auto")


def _check_clause(clause: RuleClause, bag: dict[str, Any]) -> bool:
    actual = bag.get(clause.field)
    want = clause.value
    op = clause.op
    if op == "==":
        return actual == want
    if op == "!=":
        return actual != want
    if op == ">":
        return _to_float(actual) > _to_float(want)
    if op == ">=":
        return _to_float(actual) >= _to_float(want)
    if op == "<":
        return _to_float(actual) < _to_float(want)
    if op == "<=":
        return _to_float(actual) <= _to_float(want)
    if op == "in":
        return isinstance(want, list) and actual in want
    if op == "contains":
        if isinstance(actual, str):
            return str(want) in actual
        if isinstance(actual, list):
            return want in actual
        return False
    return False


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _extract_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        rows = raw.get("rows")
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return []


def compact_dataset_for_plan(dataset: DataSet, metric_plan: MetricPlan) -> DataSet:
    required: set[str] = set(metric_plan.group_by)
    required.add(dataset.weight_field)
    if dataset.timestamp_field:
        required.add(dataset.timestamp_field)
    for metric in metric_plan.metrics:
        if metric.field:
            required.add(metric.field)
        required.update(str(k) for k in metric.where.keys())
    compact_rows: list[dict[str, Any]] = []
    for row in dataset.rows:
        if not isinstance(row, dict):
            continue
        compact_rows.append({k: row.get(k) for k in required if k})
    return DataSet(
        dataset_id=dataset.dataset_id,
        rows=compact_rows,
        timestamp_field=dataset.timestamp_field,
        window_start_ts=dataset.window_start_ts,
        window_end_ts=dataset.window_end_ts,
        weight_field=dataset.weight_field,
    )


def _select_dataset_for_compute(
    dataset: DataSet,
    metric_plan: MetricPlan,
    *,
    optimize_dataset: bool | str,
) -> DataSet:
    if optimize_dataset is False:
        return dataset
    if optimize_dataset is True:
        return compact_dataset_for_plan(dataset, metric_plan)
    if str(optimize_dataset).lower() != "auto":
        return dataset
    if not dataset.rows:
        return dataset

    required: set[str] = set(metric_plan.group_by)
    required.add(dataset.weight_field)
    if dataset.timestamp_field:
        required.add(dataset.timestamp_field)
    for metric in metric_plan.metrics:
        if metric.field:
            required.add(metric.field)
        required.update(str(k) for k in metric.where.keys())
    required.discard("")
    if not required:
        return dataset

    sample_size = min(128, len(dataset.rows))
    sample_rows = dataset.rows[:sample_size]
    key_count_total = 0
    valid_rows = 0
    for row in sample_rows:
        if not isinstance(row, dict):
            continue
        valid_rows += 1
        key_count_total += len(row)
    if valid_rows == 0:
        return dataset
    avg_keys = key_count_total / valid_rows
    required_ratio = len(required) / max(1.0, avg_keys)

    # 50w+ rows avoid another full-copy unless we can drop enough columns.
    if len(dataset.rows) >= 500_000 and required_ratio >= 0.5:
        return dataset
    if len(dataset.rows) >= 200_000 and required_ratio >= 0.7:
        return dataset
    return compact_dataset_for_plan(dataset, metric_plan)
