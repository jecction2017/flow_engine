"""Coordinator: assign deployments to workers, fail-over dead workers, drive scheduler.

设计文档 §8.4 + §8.5。Coordinator 为单实例服务（多实例运行时仍可工作但
依赖 ``uk_fe_worker_assignment_dep_worker`` 防重）。
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
    FeFlowDeployment,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.runner.scheduler import Scheduler

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
SCHEDULER_TICK_S = float(os.environ.get("FLOW_SCHEDULER_TICK_S", "30"))
DEAD_THRESHOLD_S = float(os.environ.get("FLOW_COORDINATOR_DEAD_THRESHOLD_S", "30"))
LEADER_LEASE_S = float(os.environ.get("FLOW_COORDINATOR_LEASE_S", "60"))


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


def _assign_pending_sync() -> int:
    """Assign all pending deployments and return the number of assignments created."""
    created = 0
    pending = _list_pending_deployments()
    if not pending:
        return 0
    workers = _list_active_workers()
    if not workers:
        logger.info("no active workers; %d pending deployments wait", len(pending))
        return 0

    now = _now()
    lease_until = now + timedelta(seconds=LEADER_LEASE_S)

    with db_session() as s:
        for dep in pending:
            wp = dep["worker_policy"] or {}
            wp_type = wp.get("type", "single_active")
            min_workers = max(1, int(wp.get("min_workers", 1)))

            existing_stmt = (
                select(FeWorkerAssignment.worker_id)
                .where(FeWorkerAssignment.deployment_id == dep["id"])
                .where(FeWorkerAssignment.deleted_at.is_(None))
            )
            existing = set(s.execute(existing_stmt).scalars().all())
            picks = [w for w in workers if w not in existing][:min_workers]

            if wp_type == "multi_active":
                for w in picks:
                    s.add(
                        FeWorkerAssignment(
                            deployment_id=dep["id"],
                            worker_id=w,
                            role="replica",
                            lease_expires_at=None,
                        )
                    )
                    created += 1
            else:
                # single_active
                if not picks:
                    continue
                leader_w = picks[0]
                s.add(
                    FeWorkerAssignment(
                        deployment_id=dep["id"],
                        worker_id=leader_w,
                        role="leader",
                        lease_expires_at=lease_until,
                    )
                )
                created += 1
                for w in picks[1:]:
                    s.add(
                        FeWorkerAssignment(
                            deployment_id=dep["id"],
                            worker_id=w,
                            role="standby",
                            lease_expires_at=None,
                        )
                    )
                    created += 1

            # Mark deployment running (we have at least one assignment now).
            dep_row = s.get(FeFlowDeployment, dep["id"])
            if dep_row is not None and dep_row.status == "pending":
                dep_row.status = "running"
    return created


def _check_dead_workers_sync() -> int:
    """Promote / re-assign assignments owned by dead workers. Returns # actions taken."""
    actions = 0
    dead_ids = _list_dead_workers()
    if not dead_ids:
        return 0
    active_ids = set(_list_active_workers()) - set(dead_ids)
    now = _now()
    lease_until = now + timedelta(seconds=LEADER_LEASE_S)

    with db_session() as s:
        for dead in dead_ids:
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
                    else:
                        # No standby → re-queue the deployment.
                        dep_row = s.get(FeFlowDeployment, a.deployment_id)
                        if dep_row is not None and dep_row.status == "running":
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
                    candidates = [w for w in active_ids if w not in held]
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


# ---------------------------------------------------------------------------
# Coordinator class
# ---------------------------------------------------------------------------


class Coordinator:
    def __init__(self) -> None:
        self.scheduler = Scheduler()
        self._stop_evt = asyncio.Event()
        self._last_scheduler_tick: float = 0.0

    async def stop(self) -> None:
        self._stop_evt.set()

    async def run(self) -> None:
        logger.info("coordinator started")
        try:
            while not self._stop_evt.is_set():
                started = time.monotonic()
                try:
                    await asyncio.to_thread(_assign_pending_sync)
                    await asyncio.to_thread(_check_dead_workers_sync)
                except Exception:  # noqa: BLE001
                    logger.exception("coordinator tick failed")

                if (time.monotonic() - self._last_scheduler_tick) >= SCHEDULER_TICK_S:
                    self._last_scheduler_tick = time.monotonic()
                    await self.scheduler.tick()

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
