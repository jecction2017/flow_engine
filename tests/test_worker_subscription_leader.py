"""Worker subscription leader / standby gating."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flow_engine.runner.worker import _can_consume_subscription


def _dep(wp_type: str = "single_active") -> dict:
    return {"worker_policy": {"type": wp_type, "target_workers": 1}}


def test_single_active_standby_cannot_consume() -> None:
    assert (
        _can_consume_subscription(
            _dep("single_active"),
            {"role": "standby", "lease_expires_at": None},
        )
        is False
    )


def test_single_active_leader_with_valid_lease() -> None:
    lease = datetime.now(timezone.utc) + timedelta(seconds=120)
    assert (
        _can_consume_subscription(
            _dep("single_active"),
            {"role": "leader", "lease_expires_at": lease},
        )
        is True
    )


def test_single_active_leader_expired_lease() -> None:
    lease = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (
        _can_consume_subscription(
            _dep("single_active"),
            {"role": "leader", "lease_expires_at": lease},
        )
        is False
    )


def test_multi_active_replica_can_consume() -> None:
    assert (
        _can_consume_subscription(
            _dep("multi_active"),
            {"role": "replica", "lease_expires_at": None},
        )
        is True
    )
