"""Persistence + test_runner integration tests (SQLite via conftest)."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.models import FlowDefinition
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.runner import persistence
from flow_engine.runner.models import RunMode, RunOptions
from flow_engine.stores.version_store import FlowVersionRegistry


def _flow(y: str) -> FlowDefinition:
    return compile_flow(FlowDefinition.model_validate(yaml.safe_load(y)))


@pytest.mark.asyncio
async def test_persist_once_run_writes_node_runs_not_stats() -> None:
    flow = _flow(
        """
        name: f
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
            boundary:
              outputs: {x: "$.global.x"}
        """
    )
    rt = FlowRuntime(flow, run_opts=RunOptions(mode=RunMode.PRODUCTION))
    res = await rt.run()
    run_id = persistence.create_flow_run(
        deployment_id=10,
        test_batch_id=None,
        worker_id="w1",
        flow_code="f",
        ver_no=1,
        mode=RunMode.PRODUCTION,
        trigger_context={"input": "value"},
    )
    persistence.complete_flow_run(run_id, res, is_resident=False)

    detail = persistence.get_flow_run_detail(run_id)
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["node_runs"] is not None
    assert detail["node_stats"] is None
    # node_runs is a list of dicts, one per node
    assert any(r["node_id"] == "a" for r in detail["node_runs"])


@pytest.mark.asyncio
async def test_persist_resident_run_writes_node_stats_not_runs() -> None:
    flow = _flow(
        """
        name: f
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
        """
    )
    rt = FlowRuntime(flow)
    res = await rt.run()
    run_id = persistence.create_flow_run(
        deployment_id=11,
        test_batch_id=None,
        worker_id="w1",
        flow_code="f",
        ver_no=1,
        mode=RunMode.PRODUCTION,
        trigger_context=None,
    )
    persistence.complete_flow_run(run_id, res, is_resident=True)

    detail = persistence.get_flow_run_detail(run_id)
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["node_stats"] is not None
    assert detail["node_runs"] is None
    assert "per_node" in detail["node_stats"]


@pytest.mark.asyncio
async def test_test_runner_creates_batch_and_runs() -> None:
    """End-to-end: lookup ns rows → run_test_batch → fe_flow_test_batch + fe_flow_run rows."""
    from flow_engine.lookup.lookup_service import put_table
    from flow_engine.runner import test_runner
    from flow_engine.runner.models import MockConfig, MockMode

    # Set up a flow version
    registry = FlowVersionRegistry()
    flow_dict = {
        "display_name": "test-flow",
        "version": "1.0.0",
        "strategies": {"default_sync": {"name": "default_sync", "mode": "sync"}},
        "nodes": [
            {
                "id": "n1",
                "type": "task",
                "strategy_ref": "default_sync",
                "script": '{"out": cn}',
                "boundary": {
                    "inputs": {"$.global.cn": "cn"},
                    "outputs": {"out": "$.global.result_key"},
                },
            }
        ],
    }
    registry.create("test_flow", flow_dict)
    registry.version_store("test_flow").commit_version(flow_dict)

    # Set up test rows in a lookup namespace
    test_rows = [{"cn": "case_1"}, {"cn": "case_2"}, {"cn": "case_3"}]
    put_table("test_cases", {"rows": test_rows}, profile="default")

    batch_id = await test_runner.run_test_batch(
        flow_code="test_flow",
        ver_no=1,
        test_ns_code="test_cases",
        profile_code="default",
        mock_config={
            "n1": MockConfig(mode=MockMode.FIXED, result={"out": "mocked"}),
        },
        concurrency=2,
    )

    info = test_runner.get_test_batch(batch_id)
    assert info is not None
    assert info["status"] == "completed"
    assert info["total_runs"] == 3
    assert info["completed_runs"] == 3
    assert info["error_runs"] == 0

    runs = persistence.list_flow_runs(test_batch_id=batch_id)
    assert runs["total"] == 3
    for r in runs["runs"]:
        assert r["mode"] == "debug"
        assert r["status"] == "completed"
