"""Unit tests for ``flow_engine.runner.mode_context`` (CapabilityPolicy)."""

from __future__ import annotations

import asyncio

import pytest

from flow_engine.runner.mode_context import (
    check_capability,
    effective_policy_snapshot,
    get_run_mode,
    node_capability_scope,
    run_mode_scope,
)
from flow_engine.runner.models import (
    CapabilityAction,
    CapabilityRule,
    RunMode,
)


def test_default_policy_debug_suppresses_db_write() -> None:
    with run_mode_scope(RunMode.DEBUG, []):
        action, _ = check_capability("db_write", "db_upsert")
        assert action == CapabilityAction.SUPPRESS
        assert get_run_mode() == RunMode.DEBUG


def test_default_policy_production_allows_all() -> None:
    with run_mode_scope(RunMode.PRODUCTION, []):
        action, _ = check_capability("db_write", "db_upsert")
        assert action == CapabilityAction.ALLOW


def test_deployment_rule_overrides_system_default() -> None:
    deployment_rules = [
        CapabilityRule(builtin_name="db_upsert", action=CapabilityAction.ALLOW),
    ]
    with run_mode_scope(RunMode.DEBUG, deployment_rules):
        action, _ = check_capability("db_write", "db_upsert")
        assert action == CapabilityAction.ALLOW
        # Other db_write builtins still suppress (only db_upsert is overridden by name).
        action2, _ = check_capability("db_write", "db_other")
        assert action2 == CapabilityAction.SUPPRESS


def test_node_overrides_take_priority_over_deployment() -> None:
    deployment_rules = [
        CapabilityRule(builtin_category="db_write", action=CapabilityAction.SUPPRESS),
    ]
    node_rules = [
        CapabilityRule(builtin_category="db_write", action=CapabilityAction.REDIRECT,
                       redirect_params={"profile_code": "shadow"}),
    ]
    with run_mode_scope(RunMode.PRODUCTION, deployment_rules):
        action, _ = check_capability("db_write", "db_upsert")
        assert action == CapabilityAction.SUPPRESS
        with node_capability_scope(node_rules):
            action2, params = check_capability("db_write", "db_upsert")
            assert action2 == CapabilityAction.REDIRECT
            assert params == {"profile_code": "shadow"}
        # After exiting node scope, deployment rule kicks back in.
        action3, _ = check_capability("db_write", "db_upsert")
        assert action3 == CapabilityAction.SUPPRESS


def test_unknown_builtin_defaults_to_allow() -> None:
    with run_mode_scope(RunMode.DEBUG, []):
        action, _ = check_capability("unknown_category", "anything")
        assert action == CapabilityAction.ALLOW


def test_effective_policy_snapshot_merges_node_then_base() -> None:
    deployment_rules = [
        CapabilityRule(builtin_category="db_write", action=CapabilityAction.SUPPRESS),
    ]
    node_rules = [
        CapabilityRule(builtin_name="special", action=CapabilityAction.ALLOW),
    ]
    with run_mode_scope(RunMode.DEBUG, deployment_rules):
        with node_capability_scope(node_rules):
            snap = effective_policy_snapshot()
    # node rule appears first (higher priority), then deployment rules,
    # then system defaults.
    assert len(snap) >= 4
    assert snap[0].builtin_name == "special"
    assert snap[1].builtin_category == "db_write"


@pytest.mark.asyncio
async def test_concurrent_async_tasks_have_isolated_context() -> None:
    """Two asyncio tasks running with different scopes do not see each other's policy."""

    seen: dict[str, CapabilityAction] = {}

    async def task(label: str, mode: RunMode) -> None:
        with run_mode_scope(mode, []):
            await asyncio.sleep(0.01)  # yield so the other task races
            action, _ = check_capability("db_write", "x")
            seen[label] = action

    await asyncio.gather(
        task("debug", RunMode.DEBUG),
        task("prod", RunMode.PRODUCTION),
    )
    assert seen == {
        "debug": CapabilityAction.SUPPRESS,
        "prod": CapabilityAction.ALLOW,
    }
