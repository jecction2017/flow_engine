"""YAML loading and default strategy injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from flow_engine.engine.compiler import compile_flow
from flow_engine.engine.models import ExecutionStrategy, FlowDefinition, StrategyMode


def load_flow_from_yaml(path: str | Path) -> FlowDefinition:
    raw = Path(path).read_text(encoding="utf-8")
    data: dict[str, Any] = yaml.safe_load(raw)
    strategies = dict(data.get("strategies") or {})
    if "default_sync" not in strategies:
        strategies["default_sync"] = ExecutionStrategy(name="default_sync", mode=StrategyMode.SYNC)
    data["strategies"] = strategies
    flow = FlowDefinition.model_validate(data)
    return compile_flow(flow)
