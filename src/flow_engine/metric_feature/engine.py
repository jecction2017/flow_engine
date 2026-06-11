"""High-performance metric and feature computation engine."""

from __future__ import annotations

import ast
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from flow_engine.metric_feature.models import DataSet, FeaturePlan, FeatureSnapshot, MetricDefinition, MetricPlan

try:  # pragma: no cover - optional dependency
    import polars as pl  # type: ignore
except Exception:  # noqa: BLE001
    pl = None


@dataclass(slots=True)
class _Bucket:
    key: dict[str, Any]
    rows: list[dict[str, Any]]


def compute_snapshots(
    dataset: DataSet,
    metric_plan: MetricPlan,
    feature_plan: FeaturePlan | None = None,
    *,
    feature_schema_version: str = "v1",
    feature_set_id: str = "default",
) -> list[FeatureSnapshot]:
    if pl is not None:
        try:
            return _compute_with_polars(
                dataset,
                metric_plan,
                feature_plan,
                feature_schema_version=feature_schema_version,
                feature_set_id=feature_set_id,
            )
        except Exception:  # noqa: BLE001
            pass
    return _compute_with_python(
        dataset,
        metric_plan,
        feature_plan,
        feature_schema_version=feature_schema_version,
        feature_set_id=feature_set_id,
    )


def _compute_with_polars(
    dataset: DataSet,
    metric_plan: MetricPlan,
    feature_plan: FeaturePlan | None,
    *,
    feature_schema_version: str,
    feature_set_id: str,
) -> list[FeatureSnapshot]:
    assert pl is not None
    if not dataset.rows:
        return []
    df = pl.DataFrame(dataset.rows)
    if dataset.timestamp_field and dataset.timestamp_field in df.columns:
        if dataset.window_start_ts is not None:
            df = df.filter(pl.col(dataset.timestamp_field) >= float(dataset.window_start_ts))
        if dataset.window_end_ts is not None:
            df = df.filter(pl.col(dataset.timestamp_field) <= float(dataset.window_end_ts))
    if df.height == 0:
        return []

    rows = _compute_polars_metrics(
        df,
        metric_plan.group_by,
        metric_plan.metrics,
        weight_field=dataset.weight_field,
    )
    snapshots: list[FeatureSnapshot] = []
    for row in rows:
        key = {k: row.get(k) for k in metric_plan.group_by}
        metrics = {k: v for k, v in row.items() if k not in key}
        features = _compute_features(metrics, feature_plan)
        snapshots.append(
            FeatureSnapshot(
                feature_schema_version=feature_schema_version,
                feature_set_id=feature_set_id,
                group_key=key,
                metrics=metrics,
                features=features,
            )
        )
    return snapshots


def _compute_polars_metrics(
    df: Any,
    group_by: list[str],
    specs: list[MetricDefinition],
    *,
    weight_field: str,
) -> list[dict[str, Any]]:
    assert pl is not None
    if not group_by:
        return [_compute_metrics_for_partition(df.to_dicts(), specs, weight_field=weight_field)]

    available_columns = set(df.columns)
    exprs: list[Any] = []
    unsupported: list[MetricDefinition] = []
    ratio_specs: list[MetricDefinition] = []
    for spec in specs:
        if spec.op == "ratio":
            ratio_specs.append(spec)
            continue
        expr = _spec_to_polars_expr(spec, weight_field=weight_field, available_columns=available_columns)
        if expr is None:
            unsupported.append(spec)
            continue
        exprs.append(expr.alias(spec.name))

    if exprs:
        metric_df = df.group_by(group_by, maintain_order=True).agg(*exprs)
    else:
        metric_df = df.group_by(group_by, maintain_order=True).agg(pl.len().alias("__dummy__")).drop("__dummy__")

    rows = metric_df.to_dicts()
    if unsupported:
        by_key: dict[tuple[Any, ...], dict[str, Any]] = {tuple(row.get(k) for k in group_by): row for row in rows}
        partitions = df.partition_by(group_by, maintain_order=True, as_dict=True)
        for key_tuple, part in partitions.items():
            if not isinstance(key_tuple, tuple):
                key_tuple = (key_tuple,)
            row = by_key.setdefault(key_tuple, {group_by[i]: key_tuple[i] for i in range(len(group_by))})
            fallback = _compute_metrics_for_partition(part.to_dicts(), unsupported, weight_field=weight_field)
            row.update(fallback)

    for row in rows:
        for spec in ratio_specs:
            num = _num(row.get(spec.numerator or "", 0))
            den = _num(row.get(spec.denominator or "", 0))
            row[spec.name] = 0.0 if den == 0 else num / den
    return rows


def _spec_to_polars_expr(
    spec: MetricDefinition,
    *,
    weight_field: str,
    available_columns: set[str],
) -> Any | None:
    assert pl is not None
    if spec.op == "count":
        if weight_field and weight_field in available_columns:
            weight_col = pl.col(weight_field).fill_null(1).cast(pl.Int64, strict=False)
        else:
            weight_col = pl.lit(1)
        if not spec.where:
            return weight_col.sum()
        cond = _where_to_polars_condition(spec.where, available_columns=available_columns)
        if cond is None:
            return None
        return pl.when(cond).then(weight_col).otherwise(0).sum()
    if spec.op == "distinct_count":
        if spec.where:
            return None
        if not spec.field or spec.field not in available_columns:
            return None
        return pl.col(spec.field).n_unique()
    if spec.op in {"sum", "avg", "max", "min", "percentile"}:
        if not spec.field or spec.field not in available_columns:
            return None
        expr = pl.col(spec.field)
        if spec.where:
            cond = _where_to_polars_condition(spec.where, available_columns=available_columns)
            if cond is None:
                return None
            expr = pl.when(cond).then(expr).otherwise(None)
        if spec.op == "sum":
            return expr.sum()
        if spec.op == "avg":
            return expr.mean()
        if spec.op == "max":
            return expr.max()
        if spec.op == "min":
            return expr.min()
        if spec.op == "percentile":
            return expr.quantile(float(spec.percentile or 50) / 100)
    return None


def _where_to_polars_condition(where: dict[str, Any], *, available_columns: set[str]) -> Any | None:
    assert pl is not None
    if not where:
        return None
    cond = None
    for key, value in where.items():
        if key not in available_columns:
            return None
        one = pl.col(key) == value
        cond = one if cond is None else (cond & one)
    return cond


def _compute_with_python(
    dataset: DataSet,
    metric_plan: MetricPlan,
    feature_plan: FeaturePlan | None,
    *,
    feature_schema_version: str,
    feature_set_id: str,
) -> list[FeatureSnapshot]:
    grouped: dict[tuple[Any, ...], _Bucket] = {}
    for row in dataset.rows:
        if dataset.timestamp_field:
            ts_value = row.get(dataset.timestamp_field)
            if dataset.window_start_ts is not None and _num(ts_value) < float(dataset.window_start_ts):
                continue
            if dataset.window_end_ts is not None and _num(ts_value) > float(dataset.window_end_ts):
                continue
        key_values = tuple(row.get(k) for k in metric_plan.group_by)
        if key_values not in grouped:
            grouped[key_values] = _Bucket(
                key={k: row.get(k) for k in metric_plan.group_by},
                rows=[],
            )
        grouped[key_values].rows.append(row)

    snapshots: list[FeatureSnapshot] = []
    for bucket in grouped.values():
        metrics = _compute_metrics_for_partition(bucket.rows, metric_plan.metrics, weight_field=dataset.weight_field)
        features = _compute_features(metrics, feature_plan)
        snapshots.append(
            FeatureSnapshot(
                feature_schema_version=feature_schema_version,
                feature_set_id=feature_set_id,
                group_key=bucket.key,
                metrics=metrics,
                features=features,
            )
        )
    return snapshots


def _compute_metrics_for_partition(
    rows: list[dict[str, Any]],
    specs: list[MetricDefinition],
    *,
    weight_field: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for spec in specs:
        filtered = _apply_filter(rows, spec.where)
        if spec.op == "count":
            out[spec.name] = sum(_weight(row, weight_field=weight_field) for row in filtered)
        elif spec.op == "distinct_count":
            values = {row.get(spec.field or "") for row in filtered if row.get(spec.field or "") is not None}
            out[spec.name] = len(values)
        elif spec.op == "sum":
            out[spec.name] = sum(_num(row.get(spec.field or "")) for row in filtered)
        elif spec.op == "avg":
            vals = [_num(row.get(spec.field or "")) for row in filtered]
            out[spec.name] = (sum(vals) / len(vals)) if vals else 0.0
        elif spec.op == "max":
            vals = [_num(row.get(spec.field or "")) for row in filtered]
            out[spec.name] = max(vals) if vals else 0.0
        elif spec.op == "min":
            vals = [_num(row.get(spec.field or "")) for row in filtered]
            out[spec.name] = min(vals) if vals else 0.0
        elif spec.op == "ratio":
            num = _num(out.get(spec.numerator or "", 0))
            den = _num(out.get(spec.denominator or "", 0))
            out[spec.name] = 0.0 if den == 0 else num / den
        elif spec.op == "topk":
            counter: Counter[Any] = Counter()
            for row in filtered:
                value = row.get(spec.field or "")
                if value is None:
                    continue
                counter[value] += _weight(row, weight_field=weight_field)
            out[spec.name] = [{"value": k, "count": v} for k, v in counter.most_common(spec.k)]
        elif spec.op == "entropy":
            counter = Counter()
            for row in filtered:
                value = row.get(spec.field or "")
                if value is None:
                    continue
                counter[value] += _weight(row, weight_field=weight_field)
            total = sum(counter.values())
            entropy = 0.0
            if total > 0:
                for value in counter.values():
                    p = value / total
                    entropy -= p * math.log(p, 2)
            out[spec.name] = entropy
        elif spec.op == "percentile":
            vals = sorted(_num(row.get(spec.field or "")) for row in filtered)
            out[spec.name] = _percentile(vals, float(spec.percentile or 50))
        elif spec.op == "freq_map_count":
            total = 0.0
            key_filter = {str(item) for item in spec.map_keys}
            for row in filtered:
                total += _freq_map_count(row.get(spec.field or ""), key_filter, weight=_weight(row, weight_field=weight_field))
            out[spec.name] = total
        elif spec.op == "co_occur":
            expected = [str(item) for item in spec.values if str(item)]
            if not expected:
                out[spec.name] = 0.0
                continue
            expected_set = set(expected)
            seen: set[str] = set()
            for row in filtered:
                seen.update(_extract_values(row.get(spec.field or "")))
                if expected_set.issubset(seen):
                    break
            out[spec.name] = 1.0 if expected_set.issubset(seen) else 0.0
    return out


def _compute_features(metrics: dict[str, Any], feature_plan: FeaturePlan | None) -> dict[str, Any]:
    if feature_plan is None:
        return {}
    context: dict[str, Any] = dict(metrics)
    out: dict[str, Any] = {}
    for definition in feature_plan.features:
        value = _safe_eval(definition.expression, context)
        out[definition.name] = value
        context[definition.name] = value
    return out


def _apply_filter(rows: list[dict[str, Any]], where: dict[str, Any]) -> list[dict[str, Any]]:
    if not where:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        if all(row.get(k) == want for k, want in where.items()):
            out.append(row)
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if pct <= 0:
        return values[0]
    if pct >= 100:
        return values[-1]
    k = (len(values) - 1) * (pct / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] * (c - k) + values[c] * (k - f)


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _weight(row: dict[str, Any], *, weight_field: str) -> int:
    raw = row.get(weight_field, 1) if weight_field else 1
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 1


def _freq_map_count(raw: Any, key_filter: set[str], *, weight: int) -> float:
    if not isinstance(raw, dict):
        return 0.0
    total = 0.0
    for k, v in raw.items():
        key = str(k)
        if key_filter and key not in key_filter:
            continue
        total += max(0.0, _num(v))
    # row weight is typically 1 for normalized rows; support weighted merge anyway.
    return total * max(1, weight)


def _extract_values(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, dict):
        return {str(k) for k, v in raw.items() if _num(v) > 0}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return {str(raw)}


_ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.BoolOp,
    ast.Compare,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def _safe_eval(expr: str, context: dict[str, Any]) -> Any:
    node = ast.parse(expr, mode="eval")
    for item in ast.walk(node):
        if not isinstance(item, _ALLOWED_AST_NODES):
            raise ValueError(f"unsupported feature expression syntax: {expr}")
    return eval(compile(node, "<feature_expr>", "eval"), {"__builtins__": {}}, context)  # noqa: S307
