"""Coordinator + cron scheduler tests using the in-memory SQLite fixture."""

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
            worker_policy={"type": "single_active", "target_workers": 1},
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
            worker_policy={"type": "multi_active", "target_workers": 2},
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
            worker_policy={"type": "single_active", "target_workers": 1},
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


def test_renew_subscription_leader_leases() -> None:
    _add_worker("w1", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="sub_lease",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={},
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        dep_id = int(row.id)
        expired = datetime.now(timezone.utc) - timedelta(seconds=120)
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w1",
                role="leader",
                lease_expires_at=expired,
            )
        )

    renewed = coord_mod._renew_leader_leases_sync()
    assert renewed == 1
    with db_session() as s:
        assn = (
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            )
            .scalars()
            .first()
        )
        assert assn is not None
        assert assn.lease_expires_at is not None
        lease = assn.lease_expires_at
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        assert lease > datetime.now(timezone.utc)


def test_assign_pending_clears_stale_assignments() -> None:
    """Pending restart must not be blocked by orphan assignment rows."""
    _add_worker("w1", alive=True)
    dep_id = _add_deployment(status="pending")
    with db_session() as s:
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w1",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
        )

    created = coord_mod._assign_pending_sync()
    assert created == 1
    with db_session() as s:
        dep = s.get(FeFlowDeployment, dep_id)
        assert dep is not None
        assert dep.status == "running"
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert len(assn) == 1
        assert assn[0].worker_id == "w1"


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
            worker_policy={"type": "single_active", "target_workers": 1},
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


def test_reconcile_restores_standby_after_worker_returns() -> None:
    """Under-assigned running deployments must regain workers when they come back."""
    _add_worker("w1", alive=True)
    _add_worker("w2", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="standby_return",
            ver_no=1,
            mode="production",
            schedule_type="subscription",
            schedule_config={},
            worker_policy={"type": "single_active", "target_workers": 2},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        dep_id = int(row.id)
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w1",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
        )
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w2",
                role="standby",
                lease_expires_at=None,
            )
        )

    with db_session() as s:
        w2 = s.execute(select(FeWorker).where(FeWorker.worker_id == "w2")).scalar_one()
        w2.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)

    coord_mod._check_dead_workers_sync()

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
        assert assn[0].worker_id == "w1"

    with db_session() as s:
        w2 = s.execute(select(FeWorker).where(FeWorker.worker_id == "w2")).scalar_one()
        w2.status = "active"
        w2.last_heartbeat = datetime.now(timezone.utc)

    created = coord_mod._reconcile_running_assignments_sync()
    assert created >= 1

    with db_session() as s:
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert len(assn) == 2
        by_worker = {a.worker_id: a.role for a in assn}
        assert by_worker["w1"] == "leader"
        assert by_worker["w2"] == "standby"


def test_reconcile_restores_multi_active_replica_after_worker_returns() -> None:
    _add_worker("w1", alive=True)
    _add_worker("w2", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="replica_return",
            ver_no=1,
            mode="production",
            schedule_type="once",
            schedule_config={},
            worker_policy={"type": "multi_active", "target_workers": 2},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        dep_id = int(row.id)
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w1",
                role="replica",
                lease_expires_at=None,
            )
        )
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="w2",
                role="replica",
                lease_expires_at=None,
            )
        )

    with db_session() as s:
        w2 = s.execute(select(FeWorker).where(FeWorker.worker_id == "w2")).scalar_one()
        w2.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=120)

    coord_mod._check_dead_workers_sync()

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
        assert assn[0].worker_id == "w1"

    with db_session() as s:
        w2 = s.execute(select(FeWorker).where(FeWorker.worker_id == "w2")).scalar_one()
        w2.status = "active"
        w2.last_heartbeat = datetime.now(timezone.utc)

    created = coord_mod._reconcile_running_assignments_sync()
    assert created >= 1

    with db_session() as s:
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert len(assn) == 2
        assert {a.worker_id for a in assn} == {"w1", "w2"}


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
    """Cron template stays running when leader dies and another worker can take over."""
    _add_worker("dead_w", alive=False)
    _add_worker("alive_w", alive=True)
    with db_session() as s:
        dep = FeFlowDeployment(
            flow_code="cron_dead",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "target_workers": 1},
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
    coord_mod._assign_unassigned_cron_sync()

    with db_session() as s:
        row = s.get(FeFlowDeployment, dep_id)
        assert row is not None
        assert row.status == "running"
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert len(assn) == 1
        assert assn[0].worker_id == "alive_w"
        assert assn[0].role == "leader"


def test_dead_worker_cron_leader_goes_pending_without_workers() -> None:
    """Cron leader loss with no replacement worker should become pending."""
    _add_worker("dead_w", alive=False)
    with db_session() as s:
        dep = FeFlowDeployment(
            flow_code="cron_no_worker",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "target_workers": 1},
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
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                run_no=1,
                worker_id=None,
                flow_code="cron_no_worker",
                ver_no=1,
                mode="production",
                schedule_type="cron",
                trigger_type="cron",
                status="queued",
                started_at=None,
            )
        )

    coord_mod._check_dead_workers_sync()

    with db_session() as s:
        row = s.get(FeFlowDeployment, dep_id)
        assert row is not None
        assert row.status == "pending"
        assert (row.status_detail or {}).get("reason") == "no_eligible_worker"
        run = (
            s.execute(select(FeDeployRun).where(FeDeployRun.deployment_id == dep_id))
            .scalars()
            .first()
        )
        assert run is not None
        assert run.status == "failed"


def test_explicit_dead_worker_assignment_is_cleaned_up() -> None:
    """Workers marked dead on graceful stop must release assignments."""
    with db_session() as s:
        s.add(
            FeWorker(
                worker_id="stopped_w",
                host="h",
                pid=1,
                status="dead",
                last_heartbeat=datetime.now(timezone.utc),
                capabilities={"max_concurrent_flows": 4},
            )
        )
        dep_id = _add_deployment(schedule_type="cron", status="running")
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id="stopped_w",
                role="leader",
                lease_expires_at=datetime.now(timezone.utc),
            )
        )

    actions = coord_mod._check_dead_workers_sync()
    assert actions >= 1
    with db_session() as s:
        assn = list(
            s.execute(
                select(FeWorkerAssignment).where(
                    FeWorkerAssignment.deployment_id == dep_id,
                    FeWorkerAssignment.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        assert assn == []


def test_reap_orphaned_queued_cron_run_without_assignment() -> None:
    dep_id = _add_deployment(schedule_type="cron", status="running")
    with db_session() as s:
        s.add(
            FeDeployRun(
                deployment_id=dep_id,
                run_no=1,
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

    actions = coord_mod._reap_orphaned_queued_cron_runs_sync()
    assert actions >= 1
    with db_session() as s:
        run = (
            s.execute(select(FeDeployRun).where(FeDeployRun.deployment_id == dep_id))
            .scalars()
            .first()
        )
        assert run is not None
        assert run.status == "failed"
        assert run.error and "no active worker assignment" in run.error


def test_enqueue_cron_run_if_due_inserts_queued_run() -> None:
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
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    run_id = sched_mod.enqueue_cron_run_if_due(tmpl_id)
    assert run_id is not None

    with db_session() as s:
        run = s.get(FeDeployRun, int(run_id))
        assert run is not None
        assert run.status == "queued"
        assert run.trigger_type == "cron"
        assert run.schedule_type == "cron"

        dep = s.get(FeFlowDeployment, tmpl_id)
        assert dep is not None
        cfg = dep.schedule_config or {}
        assert cfg.get("last_run_at")
        assert cfg.get("next_run_at")
        assert str(cfg["last_run_at"]).endswith("Z")
        assert "." not in str(cfg["next_run_at"])

        children = list(
            s.execute(
                select(FeFlowDeployment).where(
                    FeFlowDeployment.parent_deployment_id == tmpl_id
                )
            ).scalars().all()
        )
        assert len(children) == 0


def test_enqueue_cron_run_if_due_does_not_duplicate_before_due() -> None:
    """After one enqueue, immediate second call should not add another run."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_no_dup",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "0 */1 * * *"},
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    first = sched_mod.enqueue_cron_run_if_due(tmpl_id)
    second = sched_mod.enqueue_cron_run_if_due(tmpl_id)
    assert first is not None
    assert second == first

    with db_session() as s:
        n_runs = len(
            list(
                s.execute(
                    select(FeDeployRun).where(FeDeployRun.deployment_id == tmpl_id)
                ).scalars().all()
            )
        )
        assert n_runs == 1


def test_enqueue_cron_run_if_due_skips_missed_cycles() -> None:
    """Recovery after downtime must not backfill missed cron slots."""
    pytest.importorskip("croniter")
    from flow_engine.runner import scheduler as sched_mod

    base = datetime(2026, 5, 24, 11, 28, 0, tzinfo=timezone.utc)
    now = datetime(2026, 5, 24, 11, 34, 24, tzinfo=timezone.utc)
    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_skip",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={
                "cron_expr": "*/3 * * * *",
                "last_run_at": "2026-05-24T11:28:00Z",
                "next_run_at": "2026-05-24T11:30:00Z",
            },
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        tmpl.created_at = base
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    assert sched_mod.enqueue_cron_run_if_due(tmpl_id, now=now) is None

    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == tmpl_id)
            ).scalars().all()
        )
        assert len(runs) == 0
        dep = s.get(FeFlowDeployment, tmpl_id)
        assert dep is not None
        assert dep.schedule_config.get("next_run_at") == "2026-05-24T11:36:00Z"


def test_recover_cron_clears_status_detail_and_skips_missed() -> None:
    pytest.importorskip("croniter")
    _add_worker("w1", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="cron_recover",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={
                "cron_expr": "*/3 * * * *",
                "last_run_at": "2026-05-24T11:28:00Z",
                "next_run_at": "2026-05-24T11:30:00Z",
            },
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="pending",
            status_detail={
                "reason": "no_eligible_worker",
                "message": "cron leader lost with no replacement worker",
                "ts": "2026-05-24T11:34:03.609466+00:00",
            },
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        did = int(row.id)

    coord_mod._assign_pending_sync()

    with db_session() as s:
        dep = s.get(FeFlowDeployment, did)
        assert dep is not None
        assert dep.status == "running"
        assert dep.status_detail is None
        assert dep.schedule_config.get("next_run_at") != "2026-05-24T11:30:00Z"


def test_enqueue_cron_run_if_due_skips_stopped_template() -> None:
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
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="stopped",
            env_profile_code="default",
        )
        tmpl.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        s.add(tmpl)
        s.flush()
        tmpl_id = int(tmpl.id)

    assert sched_mod.enqueue_cron_run_if_due(tmpl_id) is None
    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == tmpl_id)
            ).scalars().all()
        )
        assert len(runs) == 0


def test_assign_pending_cron_creates_leader() -> None:
    _add_worker("w1", alive=True)
    with db_session() as s:
        row = FeFlowDeployment(
            flow_code="cron_pending",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="pending",
            env_profile_code="default",
        )
        s.add(row)
        s.flush()
        did = int(row.id)

    created = coord_mod._assign_pending_sync()
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
        dep = s.get(FeFlowDeployment, did)
        assert dep is not None
        assert dep.status == "running"


def test_reconcile_running_assignments_fills_empty_cron_leader() -> None:
    _add_worker("w1", alive=True)
    with db_session() as s:
        tmpl = FeFlowDeployment(
            flow_code="cron_assign",
            ver_no=1,
            mode="production",
            schedule_type="cron",
            schedule_config={"cron_expr": "* * * * *"},
            worker_policy={"type": "single_active", "target_workers": 1},
            capability_policy=[],
            worker_targeting={},
            status="running",
            env_profile_code="default",
        )
        s.add(tmpl)
        s.flush()
        did = int(tmpl.id)

    created = coord_mod._reconcile_running_assignments_sync()
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
            run_no=1,
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
            worker_policy={"type": "single_active", "target_workers": 1},
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
                run_no=1,
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

    coord_mod._assign_unassigned_cron_sync()
    with db_session() as s:
        dep = s.get(FeFlowDeployment, did)
        assert dep is not None
        assert dep.status == "failed"
        assert (dep.status_detail or {}).get("reason") == "pin_worker_offline"
        runs = list(
            s.execute(
                select(FeDeployRun).where(FeDeployRun.deployment_id == did)
            ).scalars().all()
        )
        if runs:
            assert runs[0].status == "failed"
            assert runs[0].error and "pin worker offline" in runs[0].error


def test_claim_queued_deploy_run_fifo() -> None:
    dep_id = _add_deployment(schedule_type="cron", status="running")
    with db_session() as s:
        for i in range(2):
            s.add(
                FeDeployRun(
                    deployment_id=dep_id,
                    run_no=i + 1,
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
