"""Persistence + test_runner integration tests (SQLite via conftest).

After the observability redesign there is no more ``fe_flow_run`` table
and no more ``node_runs`` / ``node_stats`` JSON blobs on ``fe_deploy_run``.
These tests cover the new contract:

  * deploy runs only store lifecycle + counters in ``fe_deploy_run``;
    detail lives in ``fe_run_span`` / ``fe_node_metric``.
  * test runs only store lifecycle + evaluation in ``fe_test_run``;
    detail is queryable from ``fe_run_span`` via ``test_run_id``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import yaml

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.models import FlowDefinition
from flow_engine.engine.observability import RunRef
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.runner import deploy_persistence, span_persistence
from flow_engine.runner.models import RunMode, RunOptions
from flow_engine.runner.obs_backend import AsyncBufferedDBBackend, ObsRuntimeConfig
from flow_engine.stores.version_store import FlowVersionRegistry


def _flow(y: str) -> FlowDefinition:
    return compile_flow(FlowDefinition.model_validate(yaml.safe_load(y)))


@pytest.mark.asyncio
async def test_deploy_run_lifecycle_writes_spans() -> None:
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

    run_id = deploy_persistence.create_deploy_run(
        deployment_id=10,
        worker_id="w1",
        flow_code="f",
        ver_no=1,
        mode=RunMode.PRODUCTION,
        schedule_type="once",
        trigger_type="manual",
        trigger_context={"input": "value"},
    )

    backend = AsyncBufferedDBBackend(
        run_ref=RunRef(deploy_run_id=run_id),
        flow_code="f",
        obs_cfg=ObsRuntimeConfig(),  # full sampling, INFO+ logs (default)
    )
    rt = FlowRuntime(
        flow,
        run_opts=RunOptions(mode=RunMode.PRODUCTION),
        obs=backend,
        flow_code="f",
    )
    rt._obs_run_ref = RunRef(deploy_run_id=run_id)  # type: ignore[attr-defined]
    await backend.start()
    try:
        res = await rt.run()
    finally:
        await backend.drain()

    deploy_persistence.complete_deploy_run(run_id, res)

    detail = deploy_persistence.get_deploy_run_detail(run_id)
    assert detail is not None
    assert detail["status"] == "completed"
    assert detail.get("global_ns") is not None
    assert detail["global_ns"].get("x") == 1
    # Counters are populated by the flush loop.
    assert (detail.get("sampled_span_count") or 0) >= 1

    page = span_persistence.list_spans_forest(deploy_run_id=run_id, limit=50)
    # No filter applied → ``total`` equals the run's root-subtree count
    # (back-compat alias for ``total_roots``); top-level node spans are
    # the natural roots now that the synthetic flow_root span is gone.
    assert page["total"] >= 1
    assert page["total_roots"] >= 1
    assert page["total_matched"] is None  # no filter → null per contract
    assert page["truncated"] == {"matched": False, "returned": False}
    # No synthetic flow_root rows are surfaced by the API.
    assert all(s["node_type"] != "flow_root" for s in page["items"])
    # At least one real node span (the flow's "a" task) must be present
    # and act as a natural root of the forest.
    a_spans = [s for s in page["items"] if s["node_id"] == "a"]
    assert a_spans, "expected a span for task node 'a'"
    assert a_spans[0]["parent_span_id"] is None


@pytest.mark.asyncio
async def test_test_runner_creates_batch_and_runs() -> None:
    """End-to-end: lookup ns rows → run_test_batch → fe_flow_test_batch + fe_test_run rows."""
    from flow_engine.lookup.lookup_service import put_table
    from flow_engine.runner import test_persistence, test_runner
    from flow_engine.runner.models import MockConfig, MockMode

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

    runs = test_persistence.list_test_runs(test_batch_id=batch_id)
    assert runs["total"] == 3
    for r in runs["runs"]:
        assert r["mode"] == "debug"
        assert r["status"] == "completed"
