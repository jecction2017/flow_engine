"""Integration tests for orchestrator-level mock interception."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.models import FlowDefinition, FlowState, NodeState
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.runner.models import (
    FaultType,
    MockConfig,
    MockMode,
    RunMode,
    RunOptions,
)


def _flow(y: str) -> FlowDefinition:
    data: dict[str, Any] = yaml.safe_load(y)
    return compile_flow(FlowDefinition.model_validate(data))


@pytest.mark.asyncio
async def test_fixed_mock_returns_configured_dict() -> None:
    flow = _flow(
        """
        name: m
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
            boundary:
              outputs:
                x: "$.global.x"
        """
    )
    opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides={
            "a": MockConfig(mode=MockMode.FIXED, result={"x": 99}),
        },
    )
    res = await FlowRuntime(flow, run_opts=opts).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["x"] == 99


@pytest.mark.asyncio
async def test_script_mock_replaces_original_script() -> None:
    flow = _flow(
        """
        name: m
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
            boundary:
              outputs:
                x: "$.global.x"
        """
    )
    mock_script = '{"x": 42}'
    opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides={"a": MockConfig(mode=MockMode.SCRIPT, script=mock_script)},
    )
    res = await FlowRuntime(flow, run_opts=opts).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["x"] == 42


@pytest.mark.asyncio
async def test_fault_exception_propagates_as_failed() -> None:
    flow = _flow(
        """
        name: m
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
    opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides={
            "a": MockConfig(
                mode=MockMode.FAULT,
                fault_type=FaultType.EXCEPTION,
                fault_params={"message": "boom"},
            )
        },
    )
    res = await FlowRuntime(flow, run_opts=opts).run()
    assert res.state == FlowState.FAILED
    assert res.node_state["a"] == NodeState.FAILED


@pytest.mark.asyncio
async def test_fault_dirty_data_returns_dict() -> None:
    flow = _flow(
        """
        name: m
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 1}
            boundary:
              outputs:
                x: "$.global.x"
        """
    )
    opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides={
            "a": MockConfig(
                mode=MockMode.FAULT,
                fault_type=FaultType.DIRTY_DATA,
                fault_params={"result": {"x": -1}},
            )
        },
    )
    res = await FlowRuntime(flow, run_opts=opts).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["x"] == -1


@pytest.mark.asyncio
async def test_mock_overrides_skip_unknown_node() -> None:
    """mock_overrides with a non-existent node id is a silent no-op (设计 §11.3)."""
    flow = _flow(
        """
        name: m
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 5}
            boundary:
              outputs:
                x: "$.global.x"
        """
    )
    opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides={"nonexistent": MockConfig(mode=MockMode.FIXED, result={"x": 1})},
    )
    res = await FlowRuntime(flow, run_opts=opts).run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["x"] == 5


@pytest.mark.asyncio
async def test_record_replay_records_then_replays() -> None:
    """First run executes the real script and records; second run hits cache."""
    from flow_engine.lookup.lookup_service import lookup_query
    from flow_engine.lookup.lookup_store import get_lookup_store

    flow = _flow(
        """
        name: m
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 7}
            boundary:
              outputs:
                x: "$.global.x"
        """
    )
    ns = "mock_recordings_test"
    mock_cfg = MockConfig(mode=MockMode.RECORD_REPLAY, lookup_ns=ns)
    opts = RunOptions(
        mode=RunMode.DEBUG,
        mock_overrides={"a": mock_cfg},
    )

    # 1st run: cache miss → record
    res1 = await FlowRuntime(flow, run_opts=opts).run()
    assert res1.state == FlowState.COMPLETED
    assert res1.context.global_ns["x"] == 7
    rows = lookup_query(ns)
    assert len(rows) == 1
    assert rows[0]["x"] == 7
    assert "_key" in rows[0]

    # 2nd run: change the underlying node script — replay should still produce 7
    flow2 = _flow(
        """
        name: m
        strategies:
          default_sync: {name: default_sync, mode: sync}
        nodes:
          - id: a
            type: task
            strategy_ref: default_sync
            script: |
              {"x": 999}
            boundary:
              outputs:
                x: "$.global.x"
        """
    )
    res2 = await FlowRuntime(flow2, run_opts=opts).run()
    assert res2.state == FlowState.COMPLETED
    assert res2.context.global_ns["x"] == 7  # replayed, not 999
