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
    rt.ctx.global_ns["alert"] = {
        "id": "ALT-2026-0412-01",
        "severity": "HIGH",
        "title": "Suspicious outbound connection",
        "source_ip": "203.0.113.44",
        "dest_ip": "198.51.100.7",
        "indicators": [
            {"type": "ip", "value": "198.51.100.7"},
            {"type": "domain", "value": "cdn.example.invalid"},
            {
                "type": "hash",
                "value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            },
        ],
    }
    res = await rt.run()
    assert res.state == FlowState.COMPLETED
    assert res.context.global_ns["final_report"]["closed"] is True
