"""Unit tests for ``flow_engine.runner.models`` validation rules."""

from __future__ import annotations

import pytest

from flow_engine.runner.models import (
    CapabilityAction,
    CapabilityRule,
    FaultType,
    MockConfig,
    MockMode,
    RunMode,
    RunOptions,
)


def test_capability_rule_matching_priority() -> None:
    name_rule = CapabilityRule(
        builtin_name="db_upsert", action=CapabilityAction.SUPPRESS
    )
    cat_rule = CapabilityRule(
        builtin_category="db_write", action=CapabilityAction.SUPPRESS
    )
    wildcard = CapabilityRule(action=CapabilityAction.ALLOW)

    assert name_rule.matches("db_write", "db_upsert") is True
    assert name_rule.matches("db_write", "other") is False

    assert cat_rule.matches("db_write", "any") is True
    assert cat_rule.matches("mq_publish", "any") is False

    assert wildcard.matches("anything", "anything") is True


def test_mock_config_validates_script_mode() -> None:
    with pytest.raises(ValueError):
        MockConfig(mode=MockMode.SCRIPT)
    cfg = MockConfig(mode=MockMode.SCRIPT, script="result={'a':1}")
    assert cfg.script == "result={'a':1}"


def test_mock_config_validates_fixed_mode() -> None:
    with pytest.raises(ValueError):
        MockConfig(mode=MockMode.FIXED)
    cfg = MockConfig(mode=MockMode.FIXED, result={"a": 1})
    assert cfg.result == {"a": 1}


def test_mock_config_validates_record_replay() -> None:
    with pytest.raises(ValueError):
        MockConfig(mode=MockMode.RECORD_REPLAY)
    cfg = MockConfig(mode=MockMode.RECORD_REPLAY, lookup_ns="ns")
    assert cfg.record_on_miss is True


def test_mock_config_validates_fault() -> None:
    with pytest.raises(ValueError):
        MockConfig(mode=MockMode.FAULT)
    cfg = MockConfig(
        mode=MockMode.FAULT,
        fault_type=FaultType.EXCEPTION,
        fault_params={"message": "boom"},
    )
    assert cfg.fault_type == FaultType.EXCEPTION


def test_run_options_defaults() -> None:
    opts = RunOptions()
    assert opts.mode == RunMode.PRODUCTION
    assert opts.mock_overrides == {}
    assert opts.deployment_capability_policy == []
