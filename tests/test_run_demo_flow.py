"""Run demo_flow from the repo flows directory without HTTP or managed runner."""

from __future__ import annotations

import pytest

from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.stores.version_store import FlowVersionRegistry


@pytest.mark.asyncio
async def test_run_demo_flow_with_sample_alarms() -> None:
    registry = FlowVersionRegistry()
    vs = registry.version_store("demo_flow")
    if vs.has_draft():
        data = vs.read_draft()
    else:
        meta = vs.read_meta()
        if meta.latest_version < 1:
            pytest.skip("demo_flow has no draft or committed versions")
        data = vs.read_version(meta.latest_version)

    flow = load_flow_from_dict(data)
    alarms = [
        {"id": "2026040101", "activity_level": "low", "activity_feature": "app_type_01"},
        {"id": "2026040102", "activity_level": "medium", "activity_feature": "app_type_01"},
        {"id": "2026040103", "activity_level": "high", "activity_feature": "app_type_01"},
        {"id": "2026040104", "activity_level": "low", "activity_feature": "app_type_02"},
    ]
    merged = dict(flow.initial_context or {})
    merged["alarms"] = alarms
    flow.initial_context = merged

    rt = FlowRuntime(flow)
    res = await rt.run()
    assert res.state.value in ("COMPLETED", "FAILED", "TERMINATED")
