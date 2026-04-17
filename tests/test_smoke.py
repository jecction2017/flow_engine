from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from flow_engine.engine.loader import load_flow_from_yaml
from flow_engine.engine.models import FlowState
from flow_engine.engine.orchestrator import FlowRuntime


@pytest.mark.asyncio
async def test_cyber_example_completes() -> None:
    root = Path(__file__).resolve().parents[1]
    flow = load_flow_from_yaml(root / "examples" / "cyber_alert_diagnosis.yaml")
    rt = FlowRuntime(flow)
    res = await rt.run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["final_report"]["closed"] is True
