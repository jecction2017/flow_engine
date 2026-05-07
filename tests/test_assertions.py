"""Unit tests for ``runner.assertions``."""

from __future__ import annotations

from flow_engine.engine.models import FlowState
from flow_engine.runner.assertions import evaluate_assertions, strip_expect_keys


def test_strip_expect_keys() -> None:
    row = {"id": 1, "_expect": {"path": "a", "equals": 2}, "_expect.foo": "bar"}
    clean = strip_expect_keys(row)
    assert "_expect" not in clean
    assert "_expect.foo" not in clean
    assert clean["id"] == 1


def test_evaluate_no_rules_completed() -> None:
    ev = evaluate_assertions(
        flow_state=FlowState.COMPLETED,
        global_ns={"x": 1},
        rules=[],
    )
    assert ev["verdict"] == "pass"


def test_evaluate_eq_pass() -> None:
    ev = evaluate_assertions(
        flow_state=FlowState.COMPLETED,
        global_ns={"out": {"y": 2}},
        rules=[{"id": "r1", "op": "eq", "path": "out.y", "expected": 2}],
    )
    assert ev["verdict"] == "pass"
    assert ev["rules"][0]["pass"] is True


def test_evaluate_flow_failed() -> None:
    ev = evaluate_assertions(
        flow_state=FlowState.FAILED,
        global_ns={},
        rules=[{"id": "r1", "op": "eq", "path": "x", "expected": 1}],
    )
    assert ev["verdict"] == "fail"
    assert ev["rules"] == []
