from __future__ import annotations

from flow_engine.engine.context import ContextStack
from flow_engine.metric_feature.models import DataSet, FeaturePlan, MetricDefinition, MetricPlan, RuleClause, RuleDefinition
from flow_engine.metric_feature.service import (
    _select_dataset_for_compute,
    compact_dataset_for_plan,
    enrich_dataset_with_side_input,
    pipeline_contract,
    run_pipeline,
    run_pipeline_from_dict_name,
)
from flow_engine.starlark_sdk.registry_data import load_registry
from flow_engine.starlark_sdk.runtime import eval_task_script
from flow_engine.stores.data_dict import dictionary_scope


def test_generic_pipeline_core() -> None:
    dataset = DataSet(
        dataset_id="orders",
        rows=[
            {"shop_id": "s1", "order_id": "o1", "amount": 100, "is_refund": 0, "qty": 1},
            {"shop_id": "s1", "order_id": "o2", "amount": 250, "is_refund": 1, "qty": 1},
            {"shop_id": "s2", "order_id": "o3", "amount": 80, "is_refund": 0, "qty": 2},
        ],
        timestamp_field=None,
        weight_field="qty",
    )
    metric_plan = MetricPlan(
        group_by=["shop_id"],
        metrics=[
            MetricDefinition(name="order_volume", op="count"),
            MetricDefinition(name="refund_volume", op="count", where={"is_refund": 1}),
            MetricDefinition(name="refund_ratio", op="ratio", numerator="refund_volume", denominator="order_volume"),
            MetricDefinition(name="gross_amount", op="sum", field="amount"),
        ],
    )
    feature_plan = FeaturePlan(
        features=[
            {"name": "high_refund_risk", "expression": "refund_ratio >= 0.5"},
            {"name": "avg_amount_per_volume", "expression": "gross_amount / order_volume"},
        ]
    )
    rules = [
        RuleDefinition(
            rule_id="risk_refund",
            severity="high",
            score=2.0,
            all=[RuleClause(field="refund_ratio", op=">=", value=0.5)],
        )
    ]
    out = run_pipeline(dataset, metric_plan, feature_plan, rules)
    assert len(out.snapshots) == 2
    s1 = next(s for s in out.snapshots if s.group_key["shop_id"] == "s1")
    assert s1.metrics["order_volume"] == 2
    assert s1.metrics["refund_volume"] == 1
    assert s1.features["high_refund_risk"] is True
    assert len(out.matches) == 1
    assert out.matches[0].rule_id == "risk_refund"


def test_registry_has_metric_feature_builtins() -> None:
    reg = load_registry()
    names = {f["starlark_name"] for f in reg["python_functions"]}
    assert "metric_feature_compute" in names
    assert "metric_feature_rule_eval" in names
    assert "metric_feature_pipeline" in names
    assert "metric_feature_load_metric_plan" in names
    assert "metric_feature_load_feature_plan" in names
    assert "metric_feature_load_rules" in names
    assert "metric_feature_load_scenario" in names
    assert "metric_feature_pipeline_contract" in names
    assert "metric_feature_enrich_dataset" in names


def test_starlark_metric_feature_pipeline_with_dict_scenes() -> None:
    dictionary = {
        "metric_feature": {
            "scenarios": {
                "refund_risk": {
                    "metric_dsl": {
                        "rows": [
                            {"group_by": ["shop_id"], "name": "volume", "op": "count"},
                            {"name": "refund_volume", "op": "count", "where": {"is_refund": 1}},
                            {"name": "refund_ratio", "op": "ratio", "numerator": "refund_volume", "denominator": "volume"},
                        ]
                    },
                    "feature_dsl": {
                        "rows": [{"name": "is_risky", "expression": "refund_ratio >= 0.5"}]
                    },
                    "rule_dsl": {
                        "rows": [
                            {
                                "rule_id": "high_refund",
                                "enabled": True,
                                "severity": "high",
                                "score": 3,
                                "all": [{"field": "refund_ratio", "op": ">=", "value": 0.5}],
                            }
                        ]
                    },
                    "context": {"rule_set_id": "refund_risk", "feature_schema_version": "v2"},
                },
                "refund_relaxed": {
                    "metric_dsl": {
                        "rows": [
                            {"group_by": ["shop_id"], "name": "volume", "op": "count"},
                            {"name": "refund_volume", "op": "count", "where": {"is_refund": 1}},
                            {"name": "refund_ratio", "op": "ratio", "numerator": "refund_volume", "denominator": "volume"},
                        ]
                    },
                    "feature_dsl": {
                        "rows": [{"name": "is_risky", "expression": "refund_ratio >= 0.9"}]
                    },
                    "rule_dsl": {
                        "rows": [
                            {
                                "rule_id": "high_refund",
                                "enabled": True,
                                "severity": "high",
                                "score": 3,
                                "all": [{"field": "refund_ratio", "op": ">=", "value": 0.9}],
                            }
                        ]
                    },
                },
            }
        }
    }
    script = """
dataset = {
  "rows": [
    {"shop_id": "s1", "amount": 10, "is_refund": 0, "qty": 1},
    {"shop_id": "s1", "amount": 20, "is_refund": 1, "qty": 2}
  ],
  "timestamp_field": None,
  "weight_field": "qty"
}
strict = metric_feature_pipeline(dataset, dictionary_name="refund_risk")
relaxed = metric_feature_pipeline(dataset, dictionary_name="refund_relaxed")
{
  "strict_matched": len(strict["matches"]),
  "strict_schema": strict["feature_schema_version"],
  "strict_set": strict["feature_set_id"],
  "relaxed_matched": len(relaxed["matches"]),
  "snapshots": len(strict["snapshots"]),
}
""".strip()
    with dictionary_scope(dictionary):
        result, _ = eval_task_script(script, ContextStack(), {})
    assert result == {
        "strict_matched": 1,
        "strict_schema": "v2",
        "strict_set": "refund_risk",
        "relaxed_matched": 0,
        "snapshots": 1,
    }


def test_starlark_metric_feature_pipeline_dict_hot_reload() -> None:
    script = """
dataset = {
  "rows": [
    {"shop_id": "s1", "is_refund": 0},
    {"shop_id": "s1", "is_refund": 1},
  ],
  "timestamp_field": None
}
out = metric_feature_pipeline(dataset, dictionary_name="refund_risk")
{"matched": len(out["matches"])}
""".strip()
    old_dictionary = {
        "metric_feature": {
            "scenarios": {
                "refund_risk": {
                    "metric_dsl": {"rows": [
                        {"group_by": ["shop_id"], "name": "volume", "op": "count"},
                        {"name": "refund_volume", "op": "count", "where": {"is_refund": 1}},
                        {"name": "refund_ratio", "op": "ratio", "numerator": "refund_volume", "denominator": "volume"},
                    ]},
                    "feature_dsl": {"rows": []},
                    "rule_dsl": {"rows": [
                        {"rule_id": "r1", "all": [{"field": "refund_ratio", "op": ">=", "value": 0.8}]}
                    ]},
                }
            }
        }
    }
    new_dictionary = {
        "metric_feature": {
            "scenarios": {
                "refund_risk": {
                    "metric_dsl": {"rows": [
                        {"group_by": ["shop_id"], "name": "volume", "op": "count"},
                        {"name": "refund_volume", "op": "count", "where": {"is_refund": 1}},
                        {"name": "refund_ratio", "op": "ratio", "numerator": "refund_volume", "denominator": "volume"},
                    ]},
                    "feature_dsl": {"rows": []},
                    "rule_dsl": {"rows": [
                        {"rule_id": "r1", "all": [{"field": "refund_ratio", "op": ">=", "value": 0.5}]}
                    ]},
                }
            }
        }
    }
    with dictionary_scope(old_dictionary):
        old_result, _ = eval_task_script(script, ContextStack(), {})
    with dictionary_scope(new_dictionary):
        new_result, _ = eval_task_script(script, ContextStack(), {})
    assert old_result == {"matched": 0}
    assert new_result == {"matched": 1}


def test_pipeline_contract_has_six_core_stages() -> None:
    contract = pipeline_contract()
    names = [item.stage.value for item in contract.stages]
    assert names[:6] == ["fetch", "normalize", "enrich", "metric", "feature", "rule"]


def test_metric_ops_freq_map_and_co_occur() -> None:
    dataset = DataSet(
        dataset_id="access_rows",
        rows=[
            {"subject": "u1", "status_freq": {"200": 10, "500": 2}, "method": "GET"},
            {"subject": "u1", "status_freq": {"500": 3}, "method": "POST"},
            {"subject": "u2", "status_freq": {"200": 8}, "method": "GET"},
        ],
        timestamp_field=None,
        weight_field="count",
    )
    metric_plan = MetricPlan(
        group_by=["subject"],
        metrics=[
            MetricDefinition(name="status_500_total", op="freq_map_count", field="status_freq", map_keys=["500"]),
            MetricDefinition(name="has_get_post", op="co_occur", field="method", values=["GET", "POST"]),
        ],
    )
    out = run_pipeline(dataset, metric_plan, FeaturePlan(features=[]), rules=[])
    u1 = next(s for s in out.snapshots if s.group_key["subject"] == "u1")
    u2 = next(s for s in out.snapshots if s.group_key["subject"] == "u2")
    assert u1.metrics["status_500_total"] == 5.0
    assert u1.metrics["has_get_post"] == 1.0
    assert u2.metrics["status_500_total"] == 0.0
    assert u2.metrics["has_get_post"] == 0.0


def test_enrich_dataset_with_side_input() -> None:
    dataset = DataSet(
        dataset_id="d1",
        rows=[{"subject": "u1", "url_pattern": "/a"}, {"subject": "u2", "url_pattern": "/b"}],
        timestamp_field=None,
        weight_field="row_weight",
    )
    enriched = enrich_dataset_with_side_input(
        dataset,
        [{"url_pattern": "/a", "baseline": 10}, {"url_pattern": "/b", "baseline": 20}],
        key_fields=["url_pattern"],
        include_fields=["baseline"],
        prefix="url_",
    )
    row_a = next(item for item in enriched.rows if item["url_pattern"] == "/a")
    row_b = next(item for item in enriched.rows if item["url_pattern"] == "/b")
    assert row_a["url_baseline"] == 10
    assert row_b["url_baseline"] == 20


def test_compact_dataset_for_plan_removes_unused_fields() -> None:
    dataset = DataSet(
        dataset_id="d2",
        rows=[{"subject": "u1", "url": "/a", "count": 3, "noise": "drop"}],
        timestamp_field=None,
        weight_field="count",
    )
    plan = MetricPlan(
        group_by=["subject"],
        metrics=[MetricDefinition(name="uv", op="distinct_count", field="url")],
    )
    compact = compact_dataset_for_plan(dataset, plan)
    assert "noise" not in compact.rows[0]
    assert compact.rows[0]["subject"] == "u1"
    assert compact.rows[0]["url"] == "/a"


def test_select_dataset_auto_skips_copy_for_large_dense_rows() -> None:
    rows = []
    for i in range(8):
        rows.append(
            {
                "subject": "u1",
                "url_pattern": f"/a/{i}",
                "row_weight": 1,
                "status_500_count": 2,
                "status_4xx_count": 5,
            }
        )
    dataset = DataSet(dataset_id="dense", rows=rows * 80_000, timestamp_field=None, weight_field="row_weight")
    plan = MetricPlan(
        group_by=["subject"],
        metrics=[MetricDefinition(name="status_500_total", op="sum", field="status_500_count")],
    )
    selected = _select_dataset_for_compute(dataset, plan, optimize_dataset="auto")
    assert selected is dataset


def test_access_url_migration_rules_cover_old_code_signals() -> None:
    dictionary = {
        "metric_feature": {
            "scenarios": {
                "access_url_detail_v1": {
                    "metric_dsl": {
                        "rows": [
                            {"group_by": ["subject", "url_pattern"], "name": "url_access_count", "op": "count"},
                            {"name": "status_2xx_total", "op": "sum", "field": "status_2xx_count"},
                            {"name": "status_4xx_total", "op": "sum", "field": "status_4xx_count"},
                            {"name": "status_500_total", "op": "sum", "field": "status_500_count"},
                            {"name": "status_401_403_total", "op": "sum", "field": "status_401_403_count"},
                            {"name": "status_404_total", "op": "sum", "field": "status_404_count"},
                            {"name": "status_413_429_421_total", "op": "sum", "field": "status_413_429_421_count"},
                            {"name": "post_total", "op": "sum", "field": "post_count"},
                            {"name": "put_delete_total", "op": "sum", "field": "put_delete_count"},
                            {"name": "get_post_mix_total", "op": "sum", "field": "get_post_mix"},
                            {"name": "fake_xff_total", "op": "sum", "field": "fake_xff_count"},
                            {"name": "resp_size_max", "op": "max", "field": "response_length_max"},
                            {"name": "resp_size_baseline_avg", "op": "avg", "field": "latest_7d_resp_size_avg"},
                            {"name": "url_baseline_avg", "op": "avg", "field": "url_baseline_2h"},
                            {"name": "batch_crawl_weight", "op": "count", "where": {"is_batch_crawl_url": 1}},
                            {"name": "jalor_weight", "op": "count", "where": {"is_jalor_url": 1}},
                        ]
                    },
                    "feature_dsl": {
                        "rows": [
                            {"name": "is_batch_crawl_like", "expression": "batch_crawl_weight >= 80"},
                            {"name": "is_resp_spike_like", "expression": "resp_size_baseline_avg > 0 and (resp_size_max / resp_size_baseline_avg) >= 5"},
                            {"name": "is_status_jump_like", "expression": "status_2xx_total > 0 and status_4xx_total > 0"},
                            {"name": "is_status_pressure_like", "expression": "(status_401_403_total + status_404_total + status_413_429_421_total + status_500_total) >= 10"},
                            {"name": "is_high_post_with_5xx_like", "expression": "post_total >= 5 and status_500_total > 0"},
                            {"name": "is_method_conflict_like", "expression": "put_delete_total > 0 and get_post_mix_total > 0"},
                            {"name": "is_fake_xff_like", "expression": "fake_xff_total > 0"},
                            {"name": "is_hotter_than_baseline_like", "expression": "url_baseline_avg > 0 and url_access_count > url_baseline_avg"},
                        ]
                    },
                    "rule_dsl": {
                        "rows": [
                            {"rule_id": "detail_batch_crawl_like", "all": [{"field": "is_batch_crawl_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_resp_spike_like", "all": [{"field": "is_resp_spike_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_status_jump_like", "all": [{"field": "is_status_jump_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_status_pressure_like", "all": [{"field": "is_status_pressure_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_high_post_5xx_like", "all": [{"field": "is_high_post_with_5xx_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_method_conflict_like", "all": [{"field": "is_method_conflict_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_fake_xff_like", "all": [{"field": "is_fake_xff_like", "op": "==", "value": True}]},
                            {"rule_id": "detail_hotter_than_baseline_like", "all": [{"field": "is_hotter_than_baseline_like", "op": "==", "value": True}]},
                        ]
                    },
                },
                "access_url_subject_v1": {
                    "metric_dsl": {
                        "rows": [
                            {"group_by": ["subject"], "name": "total_access_count", "op": "count"},
                            {"name": "high_worth_access_count", "op": "sum", "field": "weighted_has_high_worth"},
                            {"name": "attack_target_access_count", "op": "sum", "field": "weighted_has_attack_target"},
                            {"name": "status_500_total", "op": "sum", "field": "status_500_count"},
                            {"name": "status_401_403_total", "op": "sum", "field": "status_401_403_count"},
                            {"name": "status_404_total", "op": "sum", "field": "status_404_count"},
                            {"name": "status_413_429_421_total", "op": "sum", "field": "status_413_429_421_count"},
                            {"name": "post_total", "op": "sum", "field": "post_count"},
                            {"name": "put_delete_total", "op": "sum", "field": "put_delete_count"},
                            {"name": "fake_xff_total", "op": "sum", "field": "fake_xff_count"},
                            {"name": "external_ai_access_count", "op": "sum", "field": "is_external_ai"},
                            {"name": "jalor_access_count", "op": "sum", "field": "is_jalor_url"},
                            {"name": "batch_crawl_weight", "op": "count", "where": {"is_batch_crawl_url": 1}},
                        ]
                    },
                    "feature_dsl": {
                        "rows": [
                            {"name": "high_worth_ratio", "expression": "high_worth_access_count / total_access_count"},
                            {"name": "attack_target_ratio", "expression": "attack_target_access_count / total_access_count"},
                            {"name": "has_status_pressure", "expression": "(status_401_403_total + status_404_total + status_413_429_421_total + status_500_total) >= 10"},
                            {"name": "has_high_post_with_5xx", "expression": "post_total >= 5 and status_500_total > 0"},
                            {"name": "has_method_conflict", "expression": "put_delete_total > 0 and post_total > 0"},
                            {"name": "has_fake_xff", "expression": "fake_xff_total > 0"},
                            {"name": "has_external_ai_access", "expression": "external_ai_access_count > 0"},
                            {"name": "has_jalor_access", "expression": "jalor_access_count > 0"},
                            {"name": "has_batch_crawl", "expression": "batch_crawl_weight >= 80"},
                        ]
                    },
                    "rule_dsl": {
                        "rows": [
                            {"rule_id": "subject_high_worth_ratio", "all": [{"field": "high_worth_ratio", "op": ">=", "value": 0.3}]},
                            {"rule_id": "subject_attack_target_ratio", "all": [{"field": "attack_target_ratio", "op": ">=", "value": 0.2}]},
                            {"rule_id": "subject_status_pressure", "all": [{"field": "has_status_pressure", "op": "==", "value": True}]},
                            {"rule_id": "subject_high_post_5xx", "all": [{"field": "has_high_post_with_5xx", "op": "==", "value": True}]},
                            {"rule_id": "subject_method_conflict", "all": [{"field": "has_method_conflict", "op": "==", "value": True}]},
                            {"rule_id": "subject_fake_xff", "all": [{"field": "has_fake_xff", "op": "==", "value": True}]},
                            {"rule_id": "subject_external_ai_access", "all": [{"field": "has_external_ai_access", "op": "==", "value": True}]},
                            {"rule_id": "subject_jalor_access", "all": [{"field": "has_jalor_access", "op": "==", "value": True}]},
                            {"rule_id": "subject_batch_crawl", "all": [{"field": "has_batch_crawl", "op": "==", "value": True}]},
                        ]
                    },
                },
            }
        }
    }

    detail_dataset = DataSet(
        dataset_id="detail",
        rows=[
            {
                "subject": "u1",
                "url_pattern": "/api/page/{num}",
                "row_weight": 120,
                "status_2xx_count": 10,
                "status_4xx_count": 8,
                "status_500_count": 3,
                "status_401_403_count": 4,
                "status_404_count": 4,
                "status_413_429_421_count": 2,
                "post_count": 9,
                "put_delete_count": 2,
                "get_post_mix": 1,
                "fake_xff_count": 3,
                "response_length_max": 4000,
                "latest_7d_resp_size_avg": 500,
                "url_baseline_2h": 20,
                "is_batch_crawl_url": 1,
                "is_jalor_url": 1,
                "has_high_worth": 1,
            }
        ],
        timestamp_field=None,
        weight_field="row_weight",
    )
    subject_dataset = DataSet(
        dataset_id="subject",
        rows=[
            {
                "subject": "u1",
                "row_weight": 120,
                "has_high_worth": 1,
                "has_attack_target": 1,
                "weighted_has_high_worth": 120,
                "weighted_has_attack_target": 120,
                "status_500_count": 3,
                "status_401_403_count": 4,
                "status_404_count": 4,
                "status_413_429_421_count": 2,
                "post_count": 9,
                "put_delete_count": 2,
                "fake_xff_count": 3,
                "is_external_ai": 1,
                "is_jalor_url": 1,
                "is_batch_crawl_url": 1,
            }
        ],
        timestamp_field=None,
        weight_field="row_weight",
    )

    with dictionary_scope(dictionary):
        detail_out = run_pipeline_from_dict_name(detail_dataset, dictionary_name="access_url_detail_v1")
        subject_out = run_pipeline_from_dict_name(subject_dataset, dictionary_name="access_url_subject_v1")

    detail_rule_ids = {item.rule_id for item in detail_out.matches}
    subject_rule_ids = {item.rule_id for item in subject_out.matches}

    assert "detail_batch_crawl_like" in detail_rule_ids
    assert "detail_resp_spike_like" in detail_rule_ids
    assert "detail_status_jump_like" in detail_rule_ids
    assert "detail_status_pressure_like" in detail_rule_ids
    assert "detail_high_post_5xx_like" in detail_rule_ids
    assert "detail_method_conflict_like" in detail_rule_ids
    assert "detail_fake_xff_like" in detail_rule_ids
    assert "detail_hotter_than_baseline_like" in detail_rule_ids

    assert "subject_high_worth_ratio" in subject_rule_ids
    assert "subject_attack_target_ratio" in subject_rule_ids
    assert "subject_status_pressure" in subject_rule_ids
    assert "subject_high_post_5xx" in subject_rule_ids
    assert "subject_method_conflict" in subject_rule_ids
    assert "subject_fake_xff" in subject_rule_ids
    assert "subject_external_ai_access" in subject_rule_ids
    assert "subject_jalor_access" in subject_rule_ids
    assert "subject_batch_crawl" in subject_rule_ids
