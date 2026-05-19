"""Deploy/test run persistence of flow_logs."""

from __future__ import annotations

from flow_engine.runner.deploy_persistence import _normalize_flow_logs


def test_normalize_flow_logs_truncates() -> None:
    logs = [{"level": "info", "message": "m", "ts_ms": i, "source": "on_start"} for i in range(600)]
    out = _normalize_flow_logs(logs)
    assert out is not None
    assert len(out) == 501
    assert out[-1].get("truncated") is True
