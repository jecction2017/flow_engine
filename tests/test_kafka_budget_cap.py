"""Kafka receive timeout must respect Starlark eval budget."""

from __future__ import annotations

from flow_engine.starlark_sdk.integrations._kafka_helpers import cap_kafka_timeout_ms
from flow_engine.starlark_sdk.runtime import _ExecBudget, _EXEC_BUDGET_LOCAL


def test_cap_kafka_timeout_without_budget() -> None:
    assert cap_kafka_timeout_ms(5000) == 5000


def test_cap_kafka_timeout_with_tight_budget() -> None:
    b = _ExecBudget()
    b.max_exec_ms = 5000
    b.start()
    _EXEC_BUDGET_LOCAL.budget = b
    try:
        # Simulate 4.5s already elapsed
        b._deadline = b._deadline - 4.5
        capped = cap_kafka_timeout_ms(5000, reserve_ms=400)
        assert capped <= 600
        assert capped >= 100
    finally:
        _EXEC_BUDGET_LOCAL.budget = None
