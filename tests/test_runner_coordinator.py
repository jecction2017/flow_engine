"""Coordinator + Scheduler tests using the in-memory SQLite fixture."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from flow_engine.db.models import (
    FeDeployRun,
    FeFlowDeployment,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.runner import coordinator as coord_mod
from flow_engine.runner import deploy_persistence


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
            worker_targeting={},
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
            worker_targeting={},
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


def test_assign_pending_pin_worker_offline_fails_fast() -> None:
    """mode=pin should fail-fast when the pinned worker is not active."""
    _add_worker("dead_w", alive=False)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="pin_offline",
            ver_no=1,
            mode="production",
            schedule_type="once",
            schedule_config={},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={"mode": "pin", "worker_id": "dead_w"},
            status="pending",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        dep_id = int(row.id)

    created = coord_mod._assign_pending_sync()
    assert created == 0
    with db_session() as s:
        dep = s.get(FeFlowDeployment, dep_id)
        assert dep is not None
        assert dep.status == "failed"


def test_assign_pending_pool_filters_eligible_workers() -> None:
    _add_worker("w1", alive=True)
    _add_worker("w2", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="pool_only_w2",
            ver_no=1,
            mode="production",
            schedule_type="once",
            schedule_config={},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={"mode": "pool", "worker_ids": ["w2"]},
            status="pending",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        dep_id = int(row.id)

    created = coord_mod._assign_pending_sync()
    assert created == 1
    with db_session() as s:
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert len(assn) == 1
        assert assn[0].worker_id == "w2"


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


def test_dead_worker_cron_leader_stays_running_without_standby() -> None:
    """Cron template should not flip to pending when leader dies and no standby."""
    _add_worker("dead_w", alive=False)
    _add_worker("alive_w", alive=True)
    with db_session() as s:
        dep = FeFlowDeployment(
            flow_code="cron_dead",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(dep)
        s.flush()
        dep_id = int(dep.id)
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="dead_w",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc),
            )
        )

    coord_mod._check_dead_workers_sync()

    with db_session() as s:
        row = s.get(FeFlowDeployment, dep_id)
        assert row is not None
        assert row.status == "running"


def test_scheduler_tick_enqueues_cron_deploy_run() -> None:
    """A due cron template inserts a queued FeDeployRun (no child deployment)."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_flow",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    fires = sched_mod._tick_sync()
    assert fires >= 1

    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == tmpl_id)
            ).scalars().all()
        )
        assert len(runs) == fires
        assert runs[0].status == "queued"
        assert runs[0].trigger_type == "cron"
        assert runs[0].schedule_type == "cron"

        children = list(
            s.execute(
                select(FeFlowDeployment).where(
                    FeFlowDeployment.parent_deployment_id == tmpl_id
                )
            ).scalars().all()
        )
        assert len(children) == 0


def test_scheduler_second_tick_does_not_duplicate_before_due() -> None:
    """After one enqueue, immediate second tick should not add another run (same cron slot)."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_no_dup",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "0 */1 * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    assert sched_mod._tick_sync() == 1
    assert sched_mod._tick_sync() == 0

    with db_session() as s:
        n_runs = len(
            list(
                s.execute(
                    select(FeDeployRun).where(FeDeployRun.deployment_id == tmpl_id)
                ).scalars().all()
            )
        )
        assert n_runs == 1


def test_scheduler_does_not_fire_when_cron_stopped() -> None:
    """Stopped cron templates should not enqueue new runs."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_stopped",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="stopped",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    assert sched_mod._tick_sync() == 0
    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == tmpl_id)
            ).scalars().all()
        )
        assert len(runs) == 0


def test_scheduler_does_not_fire_when_no_active_workers() -> None:
    """If no active worker can ever claim, mark template failed and do not enqueue."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_no_workers",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={"mode": "any"},
            status="running",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(tmpl)
        s.flush()
        did = int(tmpl.id)

    assert sched_mod._tick_sync() == 0
    with db_session() as s:
        dep = s.get(FeFlowDeployment, did)
        assert dep is not None
        assert dep.status == "failed"
        assert (dep.status_detail or {}).get("reason") == "no_eligible_worker"
        assert (
            s.execute(select(FeDeployRun).where(FeDeployRun.deployment_id == did))
            .scalars()
            .all()
            == []
        )

def test_assign_cron_queued_creates_leader() -> None:
    _add_worker("w1", alive=True)
    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_assign",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(tmpl)
        s.flush()
        did = int(tmpl.id)
        s.add(
            FeDeployRun(
                deployment_id=did,
                worker_id=None,
                flow_code="cron_assign",
                ver_no=1,
                mode="production",
                schedule_type="cron",
                trigger_type="cron",
                status="queued",
                started_at=None,
            )
        )

    created = coord_mod._assign_cron_queued_sync()
    assert created >= 1

    with db_session() as s:
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == did,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert len(assn) == 1
        assert assn[0].role == "leader"
        assert assn[0].worker_id == "w1"


def test_stop_closure_releases_assignments_and_marks_stopped() -> None:
    dep_id = _add_deployment(status="running")
    with db_session() as s:
        dep = s.get(FeFlowDeployment, dep_id)
        assert dep is not None
        dep.status = "stopping"
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w1",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc),
            )
        )

    actions = coord_mod._stop_stopping_deployments_sync()
    assert actions >= 2
    with db_session() as s:
        dep = s.get(FeFlowDeployment, dep_id)
        assert dep is not None
        assert dep.status == "stopped"
        assn = list(
            s.execute(
                select(FeWorkerAssignment)
                .where(FeWorkerAssignment.deployment_id == dep_id)
            ).scalars().all()
        )
        assert assn and assn[0].deleted_at is not None


def test_reaper_fails_running_run_when_worker_dead() -> None:
    # Create a dead worker (heartbeat too old) and a running deploy_run owned by it.
    _add_worker("dead_w", alive=False)
    dep_id = _add_deployment(status="running")
    with db_session() as s:
        row = FeDeployRun(
            deployment_id=dep_id,
            worker_id="dead_w",
            flow_code="dep_flow",
            ver_no=1,
            mode="production",
            schedule_type="once",
            trigger_type="manual",
            trigger_context=None,
            status="running",
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        s.add(row)
        s.flush()
        run_id = int(row.id)

    actions = coord_mod._reap_stale_runs_sync()
    assert actions >= 1
    with db_session() as s:
        run = s.get(FeDeployRun, int(run_id))
        assert run is not None
        assert run.status == "failed"
        assert run.finished_at is not None
        assert run.error and "worker lost" in run.error


def test_cron_pin_offline_fails_queued_runs() -> None:
    _add_worker("alive_w", alive=True)
    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_pin_offline",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "min_workers": 1},
            capability_policy=[],
            worker_targeting={"mode": "pin", "worker_id": "dead_w"},
            status="running",
            env_profile_code="default",
        )
        s.add(tmpl)
        s.flush()
        did = int(tmpl.id)
        s.add(
            FeDeployRun(
                deployment_id=did,
                worker_id=None,
                flow_code="cron_pin_offline",
                ver_no=1,
                mode="production",
                schedule_type="cron",
                trigger_type="cron",
                status="queued",
                started_at=None,
            )
        )

    created = coord_mod._assign_cron_queued_sync()
    assert created >= 1
    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == did)
            ).scalars().all()
        )
        assert runs
        assert runs[0].status == "failed"
        assert runs[0].finished_at is not None
        assert runs[0].error and "pin worker offline" in runs[0].error


def test_claim_queued_deploy_run_fifo() -> None:
    dep_id = _add_deployment(schedule_type="cron", status="running")
    with db_session() as s:
        for i in range(2):
            s.add(
                FeDeployRun(
                    deployment_id=dep_id,
                    worker_id=None,
                    flow_code="dep_flow",
                    ver_no=1,
                    mode="production",
                    schedule_type="cron",
                    trigger_type="cron",
                    status="queued",
                    started_at=None,
                )
            )

    r1 = deploy_persistence.claim_queued_deploy_run(dep_id, "w1")
    r2 = deploy_persistence.claim_queued_deploy_run(dep_id, "w1")
    assert r1 is not None and r2 is not None
    assert r1 < r2
