"""Runner-layer exceptions."""

from __future__ import annotations

from flow_engine.engine.exceptions import FlowEngineError


class MockCacheMissError(FlowEngineError):
    """``record_replay`` mock 在 ``record_on_miss=False`` 时未命中缓存。"""


class RunnerConfigError(FlowEngineError):
    """运行调度层配置错误（worker_policy / schedule_config 等）。"""
