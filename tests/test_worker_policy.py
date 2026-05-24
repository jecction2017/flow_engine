"""worker_policy helpers."""

from __future__ import annotations

from flow_engine.runner.worker import _role_may_execute
from flow_engine.runner.worker_policy import (
    normalize_worker_policy,
    target_workers_from_policy,
)


def test_target_workers_from_policy_prefers_new_key() -> None:
    assert target_workers_from_policy({"target_workers": 3}) == 3


def test_target_workers_from_policy_legacy_min_workers() -> None:
    assert target_workers_from_policy({"min_workers": 4}) == 4


def test_normalize_worker_policy_drops_legacy_key() -> None:
    out = normalize_worker_policy({"type": "multi_active", "min_workers": 2})
    assert out["target_workers"] == 2
    assert "min_workers" not in out


def test_role_may_execute_single_active_standby_false() -> None:
    dep = {"worker_policy": {"type": "single_active", "target_workers": 2}}
    assert _role_may_execute(dep, {"role": "standby"}) is False
    assert _role_may_execute(dep, {"role": "leader"}) is True


def test_role_may_execute_multi_active_replica_only() -> None:
    dep = {"worker_policy": {"type": "multi_active", "target_workers": 2}}
    assert _role_may_execute(dep, {"role": "replica"}) is True
    assert _role_may_execute(dep, {"role": "leader"}) is False
