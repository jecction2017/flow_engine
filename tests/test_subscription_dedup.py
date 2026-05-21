"""Subscription idempotency helpers and claim races."""

from __future__ import annotations

import threading

from sqlalchemy import func, select

from flow_engine.db.models import FeFlowDeployment, FeSubscriptionDedup
from flow_engine.db.session import db_session
from flow_engine.runner.subscription.dedup import (
    idempotency_enabled,
    idempotency_window_s,
    try_claim_message,
)


def test_idempotency_disabled_when_absent() -> None:
    assert idempotency_enabled(None) is False
    assert idempotency_enabled({}) is False
    assert idempotency_enabled({"enabled": False}) is False
    assert idempotency_window_s(None) is None


def test_idempotency_enabled_with_window() -> None:
    raw = {"window_s": 3600}
    assert idempotency_enabled(raw) is True
    assert idempotency_window_s(raw) == 3600


def test_try_claim_message_concurrent_once_true() -> None:
    with db_session() as s:
        dep = FeFlowDeployment(
            flow_code="dedup_flow",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={},
            worker_policy={},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(dep)
        s.flush()
        dep_id = int(dep.id)

    results: list[bool] = []

    def _claim() -> None:
        results.append(
            try_claim_message(
                deployment_id=dep_id,
                topic="t",
                partition=0,
                offset=42,
                window_s=None,
            )
        )

    threads = [threading.Thread(target=_claim) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 1
    with db_session() as s:
        n = s.execute(
            select(func.count())
            .select_from(FeSubscriptionDedup)
            .where(FeSubscriptionDedup.deployment_id == dep_id)
        ).scalar_one()
    assert int(n) == 1
