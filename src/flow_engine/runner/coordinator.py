"""Coordinator: assign deployments to workers and fail-over dead workers.

设计文档 §8.4 + §8.5。Coordinator 为单实例服务（多实例运行时仍可工作但
依赖 ``uk_fe_worker_assignment_dep_worker`` 防重）。Cron 定时由已分配的 Worker
本地触发；Coordinator 只负责分配 / 续租 / 故障转移。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import (
    FeDeployRun,
    FeFlowDeployment,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.runner import scheduler
from flow_engine.runner.worker_policy import (
    policy_type_from_policy,
    target_workers_from_policy,
)

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - optional dependency guard
        return
    load_dotenv()


_load_dotenv()

# Tunables
COORDINATOR_TICK_S = float(os.environ.get("FLOW_COORDINATOR_TICK_S", "5"))
DEAD_THRESHOLD_S = float(os.environ.get("FLOW_COORDINATOR_DEAD_THRESHOLD_S", "30"))
LEADER_LEASE_S = float(os.environ.get("FLOW_COORDINATOR_LEASE_S", "60"))
RUN_REAPER_GRACE_S = float(os.environ.get("FLOW_COORDINATOR_RUN_REAPER_GRACE_S", "60"))


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _list_pending_deployments() -> list[dict[str, Any]]:
    with db_session() as s:
        stmt = (
            select(FeFlowDeployment)
            .where(FeFlowDeployment.status == "pending")
            .where(FeFlowDeployment.deleted_at.is_(None))
        )
        return [
            {
                "id": r.id,
                "flow_code": r.flow_code,
                "schedule_type": r.schedule_type,
                "worker_policy": r.worker_policy,
                "worker_targeting": getattr(r, "worker_targeting", None) or {},
            }
            for r in s.execute(stmt).scalars().all()
        ]


def _list_active_workers() -> list[str]:
    cutoff = _now() - timedelta(seconds=DEAD_THRESHOLD_S)
    with db_session() as s:
        stmt = (
            select(FeWorker.worker_id)
            .where(FeWorker.status == "active")
            .where(FeWorker.last_heartbeat > cutoff)
            .where(FeWorker.deleted_at.is_(None))
            .order_by(FeWorker.worker_id)
        )
        return list(s.execute(stmt).scalars().all())


def _list_dead_workers() -> list[str]:
    cutoff = _now() - timedelta(seconds=DEAD_THRESHOLD_S)
    with db_session() as s:
        stmt = (
            select(FeWorker.worker_id)
            .where(FeWorker.status == "active")
            .where(FeWorker.last_heartbeat <= cutoff)
            .where(FeWorker.deleted_at.is_(None))
        )
        return list(s.execute(stmt).scalars().all())


def _list_failover_worker_ids() -> list[str]:
    """Workers whose assignments must be released (stale heartbeat or explicit dead)."""
    cutoff = _now() - timedelta(seconds=DEAD_THRESHOLD_S)
    with db_session() as s:
        stale = list(
            s.execute(
                select(FeWorker.worker_id)
                .where(FeWorker.status == "active")
                .where(FeWorker.last_heartbeat <= cutoff)
                .where(FeWorker.deleted_at.is_(None))
            ).scalars().all()
        )
        dead_with_assn = list(
            s.execute(
                select(FeWorker.worker_id)
                .join(
                    FeWorkerAssignment,
                    FeWorkerAssignment.worker_id == FeWorker.worker_id,
                )
                .where(FeWorker.status == "dead")
                .where(FeWorker.deleted_at.is_(None))
                .where(FeWorkerAssignment.deleted_at.is_(None))
                .distinct()
            ).scalars().all()
        )
    return list(dict.fromkeys([*stale, *dead_with_assn]))


def _deployment_has_active_assignment(s: Any, dep_id: int) -> bool:
    return (
        s.execute(
            select(FeWorkerAssignment.id)
            .where(FeWorkerAssignment.deployment_id == dep_id)
            .where(FeWorkerAssignment.deleted_at.is_(None))
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _fail_orphaned_cron_queued_runs(
    s: Any,
    dep_id: int,
    *,
    reason: str,
    now: datetime | None = None,
) -> int:
    """Fail queued cron runs so a lost worker slot does not block future fires."""
    ts = now or _now()
    queued = list(
        s.execute(
            select(FeDeployRun)
            .where(FeDeployRun.deployment_id == dep_id)
            .where(FeDeployRun.status == "queued")
            .where(FeDeployRun.trigger_type == "cron")
            .where(FeDeployRun.deleted_at.is_(None))
        ).scalars().all()
    )
    for r in queued:
        r.status = "failed"
        r.finished_at = ts
        r.error = reason
    return len(queued)


def _cron_reassignable(
    *,
    active_workers: list[str] | set[str],
    targeting_raw: Any,
    worker_policy: Any,
) -> bool:
    mode, eligible_set = _eligible_by_targeting(
        active_workers=active_workers,
        targeting_raw=targeting_raw,
    )
    if mode == "pin" and not eligible_set:
        return False
    target = target_workers_from_policy(worker_policy or {})
    return bool(eligible_set) and target > 0


def _recover_cron_deployment_schedule(
    dep_row: FeFlowDeployment,
    *,
    session: Any,
    now: datetime,
) -> None:
    """After worker (re)assignment, skip missed slots and clear stale health detail."""
    dep_row.status_detail = None
    scheduler.align_cron_next_fire(dep_row, session=session, now=now)


def _upsert_assignment(
    s: Any,
    *,
    dep_id: int,
    worker_id: str,
    role: str,
    lease_expires_at: datetime | None,
) -> None:
    """Create or revive an assignment row (see unique key on deployment_id, worker_id)."""
    with s.no_autoflush:
        row = (
            s.execute(
                select(FeWorkerAssignment)
                .where(FeWorkerAssignment.deployment_id == dep_id)
                .where(FeWorkerAssignment.worker_id == worker_id)
            )
            .scalars()
            .first()
        )
    if row is None:
        s.add(
            FeWorkerAssignment(
                deployment_id=dep_id,
                worker_id=worker_id,
                role=role,
                lease_expires_at=lease_expires_at,
            )
        )
        return

    row.deleted_at = None
    row.role = role
    row.lease_expires_at = lease_expires_at


def _normalize_targeting(raw: Any) -> dict[str, Any]:
    """Best-effort normalize; invalid shapes become mode=any (scheduler safety)."""
    if not isinstance(raw, dict):
        return {"mode": "any"}
    mode = str(raw.get("mode") or "any").strip().lower()
    if mode == "pin":
        worker_id = str(raw.get("worker_id") or "").strip()
        if worker_id:
            return {"mode": "pin", "worker_id": worker_id}
        return {"mode": "any"}
    if mode == "pool":
        worker_ids = raw.get("worker_ids")
        if isinstance(worker_ids, list):
            ids = [str(x).strip() for x in worker_ids if str(x).strip()]
            if ids:
                return {"mode": "pool", "worker_ids": list(dict.fromkeys(ids))}
        return {"mode": "any"}
    return {"mode": "any"}


def _eligible_by_targeting(
    *,
    active_workers: list[str] | set[str],
    targeting_raw: Any,
) -> tuple[str, set[str]]:
    """Return (mode, eligible_set) for the given targeting spec.

    Notes:
    - mode=pin: eligible is either {worker_id} (if active) or empty.
    - mode=pool: eligible is active ∩ pool_ids.
    - mode=any: eligible is active.
    """
    targeting = _normalize_targeting(targeting_raw or {})
    active_set = set(active_workers)
    mode = str(targeting.get("mode") or "any")
    if mode == "pin":
        w = targeting.get("worker_id")
        if isinstance(w, str) and w and w in active_set:
            return "pin", {w}
        return "pin", set()
    if mode == "pool":
        pool = targeting.get("worker_ids") or []
        pool_set = {str(x) for x in pool if str(x)}
        return "pool", active_set & pool_set
    return "any", active_set


def _stop_stopping_deployments_sync() -> int:
    """Close the loop for stop requests.

    Semantics: stopping -> immediately release assignments and mark deployment stopped.
    """
    now = _now()
    actions = 0
    with db_session() as s:
        deps = list(
            s.execute(
                select(FeFlowDeployment)
                .where(FeFlowDeployment.status == "stopping")
                .where(FeFlowDeployment.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        if not deps:
            return 0
        dep_ids = [int(d.id) for d in deps]
        assns = list(
            s.execute(
                select(FeWorkerAssignment)
                .where(FeWorkerAssignment.deployment_id.in_(dep_ids))
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        for a in assns:
            a.deleted_at = now
            actions += 1
        for d in deps:
            d.status = "stopped"
            actions += 1
    return actions


def _reap_stale_runs_sync() -> int:
    """Fail deploy runs that are stuck in running but their worker is dead/lost."""
    now = _now()
    actions = 0
    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun)
                .where(FeDeployRun.status == "running")
                .where(FeDeployRun.worker_id.is_not(None))
                .where(FeDeployRun.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        if not runs:
            return 0

        # Load workers in one query.
        worker_ids = {str(r.worker_id) for r in runs if r.worker_id}
        workers = {
            w.worker_id: w
            for w in s.execute(
                select(FeWorker).where(FeWorker.worker_id.in_(list(worker_ids)))
            )
            .scalars()
            .all()
        }
        cutoff = now - timedelta(seconds=DEAD_THRESHOLD_S)
        grace = now - timedelta(seconds=RUN_REAPER_GRACE_S)

        for r in runs:
            wid = str(r.worker_id or "")
            if not wid:
                continue
            if r.started_at and r.started_at.tzinfo is None:
                # Treat as UTC if naive.
                started_at = r.started_at.replace(tzinfo=timezone.utc)
            else:
                started_at = r.started_at
            if started_at and started_at > grace:
                continue

            w = workers.get(wid)
            last_hb = w.last_heartbeat if w is not None else None
            if last_hb is not None and last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=timezone.utc)
            worker_lost = (
                w is None
                or w.deleted_at is not None
                or w.status != "active"
                or (last_hb is not None and last_hb <= cutoff)
            )
            if not worker_lost:
                continue

            r.status = "failed"
            r.finished_at = now
            r.error = f"worker lost: {wid}"
            actions += 1
    return actions


def _assign_pending_sync() -> int:
    """Assign all pending deployments and return the number of assignments created."""
    created = 0
    pending = _list_pending_deployments()
    if not pending:
        return 0
    workers = _list_active_workers()
    if not workers:
        logger.info("no active workers; %d pending deployments wait", len(pending))

    now = _now()
    lease_until = now + timedelta(seconds=LEADER_LEASE_S)

    with db_session() as s:
        for dep in pending:
            wp = dep["worker_policy"] or {}
            wp_type = policy_type_from_policy(wp)
            target_workers = target_workers_from_policy(wp)
            existing_stmt = (
                select(FeWorkerAssignment.worker_id)
                .where(FeWorkerAssignment.deployment_id == dep["id"])
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            existing = set(s.execute(existing_stmt).scalars().all())

            mode, eligible_set = _eligible_by_targeting(
                active_workers=workers,
                targeting_raw=dep.get("worker_targeting") or {},
            )
            if mode == "pin" and not eligible_set:
                # Pin requested but worker not active: fail fast (explicit targeting contract).
                targeting = _normalize_targeting(dep.get("worker_targeting") or {})
                pin = targeting.get("worker_id")
                dep_row = s.get(FeFlowDeployment, dep["id"])
                if dep_row is not None and dep_row.status == "pending":
                    dep_row.status = "failed"
                    dep_row.status_detail = {
                        "reason": "pin_worker_offline",
                        "worker_id": pin,
                        "targeting": targeting,
                        "ts": _now().isoformat(),
                        "message": "pin worker not active",
                    }
                logger.warning("deployment pin worker not active: dep_id=%s worker_id=%s", dep["id"], pin)
                continue

            eligible = [w for w in workers if w not in existing and w in eligible_set]

            picks = eligible[:target_workers]

            if not picks and existing:
                # Stale assignments (e.g. subscription failed without release) block restart.
                for wid in existing:
                    stale_stmt = (
                        select(FeWorkerAssignment)
                        .where(FeWorkerAssignment.deployment_id == dep["id"])
                        .where(FeWorkerAssignment.worker_id == wid)
                        .where(FeWorkerAssignment.deleted_at.is_(None))
                    )
                    for a in s.execute(stale_stmt).scalars().all():
                        a.deleted_at = now
                existing = set()
                eligible = [w for w in workers if w in eligible_set]
                picks = eligible[:target_workers]

            if wp_type == "multi_active":
                for w in picks:
                    _upsert_assignment(
                        s,
                        dep_id=int(dep["id"]),
                        worker_id=w,
                        role="replica",
                        lease_expires_at=None,
                    )
                    created += 1
            else:
                # single_active
                if not picks:
                    continue
                leader_w = picks[0]
                _upsert_assignment(
                    s,
                    dep_id=int(dep["id"]),
                    worker_id=leader_w,
                    role="leader",
                    lease_expires_at=lease_until,
                )
                created += 1
                for w in picks[1:]:
                    _upsert_assignment(
                        s,
                        dep_id=int(dep["id"]),
                        worker_id=w,
                        role="standby",
                        lease_expires_at=None,
                    )
                    created += 1

            # Mark deployment running (we have at least one assignment now).
            dep_row = s.get(FeFlowDeployment, dep["id"])
            if dep_row is not None and dep_row.status == "pending":
                dep_row.status = "running"
                if str(dep_row.schedule_type or "") == "cron":
                    _recover_cron_deployment_schedule(dep_row, session=s, now=now)
    return created


def _assign_unassigned_cron_sync() -> int:
    """Assign workers to running cron deployments that have no active assignment."""
    created = 0
    workers = _list_active_workers()
    now = _now()
    lease_until = now + timedelta(seconds=LEADER_LEASE_S)

    with db_session() as s:
        cron_deps = list(
            s.execute(
                select(FeFlowDeployment)
                .where(FeFlowDeployment.schedule_type == "cron")
                .where(FeFlowDeployment.status == "running")
                .where(FeFlowDeployment.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        for dep_row in cron_deps:
            dep_id = int(dep_row.id)
            if _deployment_has_active_assignment(s, dep_id):
                continue

            wp = dep_row.worker_policy or {}
            wp_type = policy_type_from_policy(wp)
            target_workers = target_workers_from_policy(wp)

            existing_stmt = (
                select(FeWorkerAssignment.worker_id)
                .where(FeWorkerAssignment.deployment_id == dep_id)
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            existing = set(s.execute(existing_stmt).scalars().all())
            mode, eligible_set = _eligible_by_targeting(
                active_workers=workers,
                targeting_raw=getattr(dep_row, "worker_targeting", None) or {},
            )
            if mode == "pin" and not eligible_set:
                targeting = _normalize_targeting(getattr(dep_row, "worker_targeting", None) or {})
                pin = targeting.get("worker_id")
                queued_failed = _fail_orphaned_cron_queued_runs(
                    s,
                    dep_id,
                    reason=f"pin worker offline: {pin}",
                    now=now,
                )
                dep_row.status = "failed"
                dep_row.status_detail = {
                    "reason": "pin_worker_offline",
                    "worker_id": pin,
                    "targeting": targeting,
                    "queued_failed": queued_failed,
                    "ts": now.isoformat(),
                    "message": "cron pin worker offline",
                }
                logger.warning(
                    "cron deployment pin worker not active: dep_id=%s worker_id=%s",
                    dep_id,
                    pin,
                )
                continue

            if not workers or not eligible_set:
                queued_failed = _fail_orphaned_cron_queued_runs(
                    s,
                    dep_id,
                    reason="no active worker available for cron assignment",
                    now=now,
                )
                dep_row.status = "pending"
                dep_row.status_detail = {
                    "reason": "no_eligible_worker",
                    "queued_failed": queued_failed,
                    "ts": now.isoformat(),
                    "message": "cron waiting for an active worker",
                }
                logger.info(
                    "cron deployment unassigned with no workers: dep_id=%s queued_failed=%s",
                    dep_id,
                    queued_failed,
                )
                continue

            eligible = [w for w in workers if w not in existing and w in eligible_set]
            picks = eligible[:target_workers]

            if wp_type == "multi_active":
                for w in picks:
                    _upsert_assignment(
                        s,
                        dep_id=dep_id,
                        worker_id=w,
                        role="replica",
                        lease_expires_at=None,
                    )
                    created += 1
            else:
                if not picks:
                    continue
                leader_w = picks[0]
                _upsert_assignment(
                    s,
                    dep_id=dep_id,
                    worker_id=leader_w,
                    role="leader",
                    lease_expires_at=lease_until,
                )
                created += 1
                for w in picks[1:]:
                    _upsert_assignment(
                        s,
                        dep_id=dep_id,
                        worker_id=w,
                        role="standby",
                        lease_expires_at=None,
                    )
                    created += 1
            _recover_cron_deployment_schedule(dep_row, session=s, now=now)
    return created


def _renew_leader_leases_sync() -> int:
    """Extend leader leases for long-running subscription and cron deployments."""
    now = _now()
    lease_until = now + timedelta(seconds=LEADER_LEASE_S)
    renewed = 0
    with db_session() as s:
        rows = list(
            s.execute(
                select(FeWorkerAssignment)
                .join(
                    FeFlowDeployment,
                    FeFlowDeployment.id == FeWorkerAssignment.deployment_id,
                )
                .where(FeFlowDeployment.schedule_type.in_(("subscription", "cron")))
                .where(FeFlowDeployment.status == "running")
                .where(FeFlowDeployment.deleted_at.is_(None))
                .where(FeWorkerAssignment.role == "leader")
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            .scalars()
            .all()
        )
        for assn in rows:
            assn.lease_expires_at = lease_until
            renewed += 1
    return renewed


def _check_dead_workers_sync() -> int:
    """Promote / re-assign assignments owned by dead workers. Returns # actions taken."""
    actions = 0
    failover_ids = _list_failover_worker_ids()
    if not failover_ids:
        return 0
    active_ids = set(_list_active_workers())
    now = _now()
    lease_until = now + timedelta(seconds=LEADER_LEASE_S)

    with db_session() as s:
        for dead in failover_ids:
            row = (
                s.execute(select(FeWorker).where(FeWorker.worker_id == dead))
                .scalar_one_or_none()
            )
            if row is not None:
                row.status = "dead"

            assn_stmt = (
                select(FeWorkerAssignment)
                .where(FeWorkerAssignment.worker_id == dead)
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            assignments = list(s.execute(assn_stmt).scalars().all())
            for a in assignments:
                if a.role == "leader":
                    # Promote a standby of the same deployment.
                    standby_stmt = (
                        select(FeWorkerAssignment)
                        .where(FeWorkerAssignment.deployment_id == a.deployment_id)
                        .where(FeWorkerAssignment.role == "standby")
                        .where(FeWorkerAssignment.deleted_at.is_(None))
                        .order_by(FeWorkerAssignment.id)
                    )
                    promoted = None
                    for cand in s.execute(standby_stmt).scalars().all():
                        if cand.worker_id in active_ids:
                            promoted = cand
                            break
                    if promoted is not None:
                        promoted.role = "leader"
                        promoted.lease_expires_at = lease_until
                        actions += 1
                        dep_row = s.get(FeFlowDeployment, a.deployment_id)
                        if (
                            dep_row is not None
                            and dep_row.schedule_type == "cron"
                            and dep_row.status == "running"
                        ):
                            _recover_cron_deployment_schedule(dep_row, session=s, now=now)
                    else:
                        dep_row = s.get(FeFlowDeployment, a.deployment_id)
                        if dep_row is not None and dep_row.status == "running":
                            if dep_row.schedule_type == "cron":
                                if not _cron_reassignable(
                                    active_workers=active_ids,
                                    targeting_raw=getattr(dep_row, "worker_targeting", None) or {},
                                    worker_policy=dep_row.worker_policy,
                                ):
                                    queued_failed = _fail_orphaned_cron_queued_runs(
                                        s,
                                        int(dep_row.id),
                                        reason=f"worker lost: {dead}",
                                        now=now,
                                    )
                                    dep_row.status = "pending"
                                    dep_row.status_detail = {
                                        "reason": "no_eligible_worker",
                                        "worker_id": dead,
                                        "queued_failed": queued_failed,
                                        "ts": now.isoformat(),
                                        "message": "cron leader lost with no replacement worker",
                                    }
                            else:
                                dep_row.status = "pending"
                            actions += 1
                elif a.role == "replica":
                    # Find another active worker not already holding this deployment.
                    held_stmt = (
                        select(FeWorkerAssignment.worker_id)
                        .where(FeWorkerAssignment.deployment_id == a.deployment_id)
                        .where(FeWorkerAssignment.deleted_at.is_(None))
                    )
                    held = set(s.execute(held_stmt).scalars().all())
                    dep_row = s.get(FeFlowDeployment, a.deployment_id)
                    mode, eligible_set = _eligible_by_targeting(
                        active_workers=active_ids,
                        targeting_raw=getattr(dep_row, "worker_targeting", None) if dep_row else {},
                    )
                    # pin means "do not replace with a different worker"
                    if mode != "pin":
                        candidates = [w for w in eligible_set if w not in held]
                    else:
                        candidates = []
                    if candidates:
                        s.add(
                            FeWorkerAssignment(
                                deployment_id=a.deployment_id,
                                worker_id=candidates[0],
                                role="replica",
                                lease_expires_at=None,
                            )
                        )
                        actions += 1
                # Soft-delete the dead worker's assignment.
                a.deleted_at = now
                actions += 1
    return actions


def _reap_orphaned_queued_cron_runs_sync() -> int:
    """Fail queued cron runs that cannot be claimed (no assignment / dead worker)."""
    now = _now()
    cutoff = now - timedelta(seconds=DEAD_THRESHOLD_S)
    actions = 0
    with db_session() as s:
        runs = list(
            s.execute(
                select(FeDeployRun)
                .where(FeDeployRun.status == "queued")
                .where(FeDeployRun.trigger_type == "cron")
                .where(FeDeployRun.deleted_at.is_(None))
            ).scalars().all()
        )
        if not runs:
            return 0

        dep_ids = {int(r.deployment_id) for r in runs}
        deps = {
            int(d.id): d
            for d in s.execute(
                select(FeFlowDeployment).where(FeFlowDeployment.id.in_(list(dep_ids)))
            ).scalars().all()
        }
        assigned_deps = {
            int(x)
            for x in s.execute(
                select(FeWorkerAssignment.deployment_id)
                .where(FeWorkerAssignment.deployment_id.in_(list(dep_ids)))
                .where(FeWorkerAssignment.deleted_at.is_(None))
                .distinct()
            ).scalars().all()
        }
        worker_ids = {str(r.worker_id) for r in runs if r.worker_id}
        workers = {
            w.worker_id: w
            for w in s.execute(
                select(FeWorker).where(FeWorker.worker_id.in_(list(worker_ids)))
            ).scalars().all()
        } if worker_ids else {}

        for r in runs:
            dep = deps.get(int(r.deployment_id))
            if dep is None or dep.deleted_at is not None:
                r.status = "failed"
                r.finished_at = now
                r.error = "orphaned: deployment missing"
                actions += 1
                continue
            if dep.status != "running":
                r.status = "failed"
                r.finished_at = now
                r.error = f"orphaned: deployment status={dep.status}"
                actions += 1
                continue
            if int(dep.id) not in assigned_deps:
                r.status = "failed"
                r.finished_at = now
                r.error = "orphaned: no active worker assignment"
                actions += 1
                continue
            wid = str(r.worker_id or "")
            if not wid:
                continue
            w = workers.get(wid)
            last_hb = w.last_heartbeat if w is not None else None
            if last_hb is not None and last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=timezone.utc)
            worker_lost = (
                w is None
                or w.deleted_at is not None
                or w.status != "active"
                or (last_hb is not None and last_hb <= cutoff)
            )
            if worker_lost:
                r.status = "failed"
                r.finished_at = now
                r.error = f"orphaned: worker lost: {wid}"
                actions += 1
    return actions


# ---------------------------------------------------------------------------
# Coordinator class
# ---------------------------------------------------------------------------


class Coordinator:
    def __init__(self) -> None:
        self._stop_evt = asyncio.Event()

    async def stop(self) -> None:
        self._stop_evt.set()

    async def run(self) -> None:
        logger.info("coordinator started")
        try:
            while not self._stop_evt.is_set():
                started = time.monotonic()
                try:
                    await asyncio.to_thread(_stop_stopping_deployments_sync)
                    await asyncio.to_thread(_assign_pending_sync)
                    await asyncio.to_thread(_check_dead_workers_sync)
                    await asyncio.to_thread(_assign_unassigned_cron_sync)
                    await asyncio.to_thread(_renew_leader_leases_sync)
                    await asyncio.to_thread(_reap_stale_runs_sync)
                    await asyncio.to_thread(_reap_orphaned_queued_cron_runs_sync)
                except Exception:  # noqa: BLE001
                    logger.exception("coordinator tick failed")

                elapsed = time.monotonic() - started
                wait = max(0.0, COORDINATOR_TICK_S - elapsed)
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=wait)
                except asyncio.TimeoutError:
                    continue
        finally:
            logger.info("coordinator stopped")


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


async def main_async() -> None:
    coord = Coordinator()
    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        if not coord._stop_evt.is_set():  # noqa: SLF001
            logger.info("signal received, stopping coordinator")
            coord._stop_evt.set()  # noqa: SLF001

    try:
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: _on_signal())
    except Exception:  # noqa: BLE001
        logger.debug("signal handlers not installed", exc_info=True)

    await coord.run()


def main(argv: list[str] | None = None) -> int:
    import argparse
    import logging as _logging

    p = argparse.ArgumentParser(prog="flow-coordinator", description="Flow Engine Coordinator")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="start the coordinator process")
    args = p.parse_args(argv)

    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.cmd == "start":
        asyncio.run(main_async())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
