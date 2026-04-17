"""End-to-end coverage tests for the curated ``data/flows/example_*.yaml``.

Each test loads a canonical flow YAML from ``data/flows`` and runs it through
``FlowRuntime``. Assertions focus on the orchestrator feature each flow is
designed to exercise (sequential pipeline, parallel fan-out + barrier,
condition branch + SKIPPED state, loop aggregation + $.item, subflow frame
isolation, jump / on_error control flow, lifecycle hooks).

Run all of them in one shot after a code change::

    pytest tests/test_example_flows.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flow_engine.engine.loader import load_flow_from_yaml
from flow_engine.engine.models import FlowState, NodeState
from flow_engine.engine.orchestrator import FlowRuntime

FLOWS_DIR = Path(__file__).resolve().parents[1] / "data" / "flows"


def _flow(name: str):
    return load_flow_from_yaml(FLOWS_DIR / f"{name}.yaml")


# --------------------------------------------------------------------------
# 1) Sequential pipeline with boundary I/O
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_example_01_sequential_pipeline() -> None:
    res = await FlowRuntime(_flow("example_01_sequential_pipeline")).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns
    assert g["normalized"] == {"id": "ORD-1001", "amount": 200.0, "vip": True}
    assert g["tax"] == pytest.approx(20.0)
    assert g["total"] == pytest.approx(220.0)
    assert g["report"] == {
        "order_id": "ORD-1001",
        "amount": 200.0,
        "tax": pytest.approx(20.0),
        "total": pytest.approx(220.0),
    }
    for nid in ("normalize", "compute_tax", "compute_total", "summarize"):
        assert res.node_state[nid] == NodeState.SUCCESS


# --------------------------------------------------------------------------
# 2) Parallel fan-out + wait_before barrier
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_example_02_parallel_fanout() -> None:
    res = await FlowRuntime(_flow("example_02_parallel_fanout")).run()
    assert res.state == FlowState.COMPLETED, res.message
    bucket = res.context.global_ns["bucket"]
    assert set(bucket.keys()) == {"a", "b", "c"}
    assert sum(v["value"] for v in bucket.values()) == 6
    agg = res.context.global_ns["aggregate"]
    assert agg["sum"] == 6
    assert agg["keys"] == ["a", "b", "c"]


# --------------------------------------------------------------------------
# 3) Conditional branch with SKIPPED nodes
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "metric_value, expected_level, expected_action, taken_id, skipped_ids",
    [
        (95, "critical", "page_oncall", "critical_branch", ["warning_branch", "ok_branch"]),
        (75, "warning", "notify_channel", "warning_branch", ["critical_branch", "ok_branch"]),
        (10, "ok", "noop", "ok_branch", ["critical_branch", "warning_branch"]),
    ],
)
@pytest.mark.asyncio
async def test_example_03_conditional_branch(
    metric_value: int,
    expected_level: str,
    expected_action: str,
    taken_id: str,
    skipped_ids: list[str],
) -> None:
    flow = _flow("example_03_conditional_branch")
    flow.initial_context = {"metric": {"value": metric_value}}
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns
    assert g["level"] == expected_level
    assert g["decision"]["action"] == expected_action
    assert g["summary"] == {"level": expected_level, "action": expected_action}
    assert res.node_state[taken_id] == NodeState.SUCCESS
    for sid in skipped_ids:
        assert res.node_state[sid] == NodeState.SKIPPED


# --------------------------------------------------------------------------
# 4) Loop aggregation with $.item + copy_item=deep
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_example_04_loop_aggregation() -> None:
    res = await FlowRuntime(_flow("example_04_loop_aggregation")).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns
    # 2*10 + 1*25 + 3*4 = 20 + 25 + 12 = 57
    assert g["totals"]["grand_total"] == 57
    rows = g["totals"]["rows"]
    assert len(rows) == 3
    assert {r["sku"] for r in rows} == {"A", "B", "C"}
    assert g["report"] == {"count": 3, "grand_total": 57}
    # Loop frame must be popped; no leaked frames at flow exit.
    assert res.context.frames == []


# --------------------------------------------------------------------------
# 5) Subflow namespace: frame must pop, globals accumulate
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_example_05_subflow_namespace() -> None:
    res = await FlowRuntime(_flow("example_05_subflow_namespace")).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns
    # before: 0+1=1 ; sub_step_1: 1+10=11 ; after: 11+100=111
    assert g["counter"] == 111
    assert g["tag"] == "enriched"
    assert res.context.frames == [], "subflow frame must be popped on exit"
    assert res.node_state["sub_enrich"] == NodeState.SUCCESS


# --------------------------------------------------------------------------
# 6) Jump + on_error + loop break
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_example_06_jump_and_error() -> None:
    res = await FlowRuntime(_flow("example_06_retry_and_jump")).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns
    # flow_jump skipped handle_slow; jump target was handle_fast.
    # on_error=jump redirected guarded_divide failure to recover (skipping never_runs).
    # on_error=ignore swallowed optional_step's error, after_optional still ran.
    assert g["trail"] == ["fast", "recover", "after_optional"]
    # Loop early-break: items=[1,2,3,4,5], limit=3 → seen=[1,2,3].
    assert g["seen"] == [1, 2, 3]
    # "never_runs" must not reach SUCCESS (it was skipped by the jump target).
    assert res.node_state.get("never_runs") != NodeState.SUCCESS
    assert res.node_state.get("handle_slow") != NodeState.SUCCESS
    assert res.node_state["recover"] == NodeState.SUCCESS
    assert res.node_state["handle_fast"] == NodeState.SUCCESS


# --------------------------------------------------------------------------
# 7) Hooks lifecycle (flow / task / loop)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_example_07_hooks_lifecycle() -> None:
    res = await FlowRuntime(_flow("example_07_hooks_lifecycle")).run()
    assert res.state == FlowState.COMPLETED, res.message
    g = res.context.global_ns
    assert g["sum"] == 60
    assert g["result"] == {"sum": 60, "avg": 20}


# --------------------------------------------------------------------------
# Catch-all sanity check: every example_*.yaml compiles and runs.
# Acts as a safety net for any newly added example file.
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "yaml_path",
    sorted(FLOWS_DIR.glob("example_*.yaml")),
    ids=lambda p: p.stem,
)
@pytest.mark.asyncio
async def test_example_flow_runs_to_completion(yaml_path: Path) -> None:
    flow = load_flow_from_yaml(yaml_path)
    res = await FlowRuntime(flow).run()
    assert res.state == FlowState.COMPLETED, f"{yaml_path.name}: {res.message}"
