"""DSL helpers for metric/feature/rule configurations."""

from __future__ import annotations

from typing import Any

from flow_engine.metric_feature.models import (
    FeaturePlan,
    MetricDefinition,
    MetricPlan,
    RuleClause,
    RuleDefinition,
)


def metric_plan_from_rows(
    rows: list[dict[str, Any]],
    *,
    plan_id: str = "lookup_metric_plan",
    default_group_by: list[str] | None = None,
) -> MetricPlan:
    group_by: list[str] = list(default_group_by or [])
    metrics: list[MetricDefinition] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if isinstance(row.get("group_by"), list):
            group_by = [str(x) for x in row.get("group_by", []) if str(x)]
        name = str(row.get("name", "")).strip()
        op = str(row.get("op", "")).strip()
        if not name or not op:
            continue
        metrics.append(
            MetricDefinition(
                name=name,
                op=op,
                field=row.get("field"),
                numerator=row.get("numerator"),
                denominator=row.get("denominator"),
                where=row.get("where", {}) if isinstance(row.get("where"), dict) else {},
                percentile=row.get("percentile"),
                k=int(row.get("k", 3) or 3),
                values=row.get("values", []) if isinstance(row.get("values"), list) else [],
                map_keys=row.get("map_keys", []) if isinstance(row.get("map_keys"), list) else [],
            )
        )
    return MetricPlan(plan_id=plan_id, group_by=group_by, metrics=metrics)


def feature_plan_from_rows(rows: list[dict[str, Any]], *, plan_id: str = "lookup_feature_plan") -> FeaturePlan:
    features: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        expression = str(row.get("expression", "")).strip()
        if name and expression:
            features.append({"name": name, "expression": expression})
    return FeaturePlan(plan_id=plan_id, features=features)


def rules_from_rows(rows: list[dict[str, Any]]) -> list[RuleDefinition]:
    out: list[RuleDefinition] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rule_id = str(row.get("rule_id", "")).strip()
        if not rule_id:
            continue
        out.append(
            RuleDefinition(
                rule_id=rule_id,
                description=str(row.get("description", "")),
                enabled=bool(row.get("enabled", True)),
                severity=str(row.get("severity", "medium")),
                score=float(row.get("score", 1.0) or 1.0),
                all=_clauses_from_rows(row.get("all")),
                any=_clauses_from_rows(row.get("any")),
                tags=[str(x) for x in row.get("tags", [])] if isinstance(row.get("tags"), list) else [],
            )
        )
    return out


def _clauses_from_rows(raw: Any) -> list[RuleClause]:
    if not isinstance(raw, list):
        return []
    out: list[RuleClause] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        op = str(item.get("op", "")).strip()
        if not field or not op:
            continue
        out.append(RuleClause(field=field, op=op, value=item.get("value")))
    return out
