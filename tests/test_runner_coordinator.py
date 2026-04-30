"""Coordinator + Scheduler tests using the in-memory SQLite fixture."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from flow_engine.db.models import (
    FeFlowDeployment,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.runner import coordinator as coord_mod


def _add_worker(worker_id: str, *, alive: bool = True) -> None:
    age = timedelta(seconds=2 if alive else 120)
    with db_session() as s:
        s.add(
            FeWorker(
                worker_id=worker_id,
                host="h",
                pid=1,
                status="active",
                last_heartbeat=datetime.now(timezone.utc) - age,
                capabilities={"max_concurrent_flows": 4},
            )
        )


def _add_deployment(*, schedule_type: str = "once", status: str = "pending") -> int:
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="dep_flow",
            ver_no=1,
            mode="production",
            schedule_type=schedule_type,
            schedule_config={},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            status=status,
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        return int(row.id)


def test_assign_pending_creates_leader_for_single_active() -> None:
    _add_worker("w1", alive=True)
    dep_id = _add_deployment()

    created = coord_mod._assign_pending_sync()
    assert created == 1

    with db_session() as s:
        assignments = (
            s.execute(
                FeWorkerAssignment.__table__.select().where(
                    FeWorkerAssignment.deployment_id == dep_id
                )
            ).fetchall()
        )
        assert len(assignments) == 1
        assert assignments[0].role == "leader"

        dep = s.get(FeFlowDeployment, dep_id)
        assert dep.status == "running"


def test_assign_pending_multi_active_assigns_each_worker() -> None:
    _add_worker("w1", alive=True)
    _add_worker("w2", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="multi",
            ver_no=1,
            mode="production",
            schedule_type="once",
            schedule_config={},
            worker_policy={"type": "multi_active", "min_workers": 2},
            capability_policy=[],
            status="pending",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        dep_id = row.id

    coord_mod._assign_pending_sync()

    with db_session() as s:
        assignments = (
            s.execute(
                FeWorkerAssignment.__table__.select().where(
                    FeWorkerAssignment.deployment_id == dep_id
                )
            ).fetchall()
        )
        assert len(assignments) == 2
        roles = {a.role for a in assignments}
        assert roles == {"replica"}


def test_dead_worker_leader_promotes_standby() -> None:
    _add_worker("dead_w", alive=False)
    _add_worker("alive_w", alive=True)
    dep_id = _add_deployment(status="running")

    with db_session() as s:
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="dead_w",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc),
            )
        )
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="alive_w",
                role="standby",
                lease_expires_at=None,
            )
        )

    actions = coord_mod._check_dead_workers_sync()
    assert actions > 0

    with db_session() as s:
        rows = (
            s.execute(
                FeWorkerAssignment.__table__.select().where(
                    FeWorkerAssignment.deployment_id == dep_id
                )
            ).fetchall()
        )
        # dead_w's row is soft-deleted; alive_w is now leader.
        roles_by_worker = {r.worker_id: (r.role, r.deleted_at is not None) for r in rows}
        assert roles_by_worker["dead_w"][1] is True  # soft-deleted
        assert roles_by_worker["alive_w"] == ("leader", False)


def test_scheduler_tick_fires_cron_due() -> None:
    """A cron template whose next_fire is in the past creates a once child."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    # Build a cron deployment created 2 hours ago, with cron expression that
    # fires every minute → next_fire is well in the past → should fire.
    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_flow",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            status="running",
            env_profile_code="default",
        )
        # Force an old created_at so the next_fire computation lands in the past.
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(tmpl)
        s.flush()
        tmpl_id = tmpl.id

    fires = sched_mod._tick_sync()
    assert fires >= 1

    with db_session() as s:
        rows = list(
            s.execute(
                FeFlowDeployment.__table__.select().where(
                    FeFlowDeployment.parent_deployment_id == tmpl_id
                )
            ).fetchall()
        )
        assert len(rows) == fires
        assert rows[0].schedule_type == "once"
        assert rows[0].status == "pending"
