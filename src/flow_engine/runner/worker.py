"""Worker process: register, heartbeat, run assigned deployments.

设计文档 §8.3。Worker 是一个独立 asyncio 进程：
* 启动：注册 ``FeWorker`` + 启动心跳与轮询两个后台 Task；
* 运行：每个 ``FeWorkerAssignment`` 关联一个 asyncio.Task；cron/subscription
  为长期任务（本地定时/消费），once 为单次执行后释放 assignment；
* 停止：取消所有 Task、回写 ``FeWorker.status='dead'``。

DB 操作均同步（SQLAlchemy）；async 调用方使用 ``asyncio.to_thread``。
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from flow_engine.db.models import (
    FeFlowDeployment,
    FeFlowVersion,
    FeWorker,
    FeWorkerAssignment,
)
from flow_engine.db.session import db_session
from flow_engine.engine.exceptions import FlowEngineError
from flow_engine.engine.loader import load_flow_from_dict
from flow_engine.engine.models import FlowState
from flow_engine.engine.observability import RunRef
from flow_engine.engine.orchestrator import FlowRuntime
from flow_engine.runner import deploy_persistence, scheduler, span_persistence
from flow_engine.runner.exceptions import RunnerConfigError
from flow_engine.runner.worker_policy import policy_type_from_policy
from flow_engine.runner.models import CapabilityRule, RunMode, RunOptions
from flow_engine.runner.obs_backend import AsyncBufferedDBBackend, parse_obs_config
from flow_engine.stores import data_dict
from flow_engine.stores.profile_store import (
    DEFAULT_PROFILE_ID,
    profile_scope,
    store as profile_store,
)

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - optional dependency guard
        return
    load_dotenv()


_load_dotenv()

# Tunables (override via env where useful for tests / staging).
HEARTBEAT_INTERVAL_S = float(os.environ.get("FLOW_WORKER_HEARTBEAT_S", "10"))
ASSIGNMENT_POLL_INTERVAL_S = float(os.environ.get("FLOW_WORKER_POLL_S", "2"))
DEAD_THRESHOLD_S = float(os.environ.get("FLOW_WORKER_DEAD_THRESHOLD_S", "30"))
# Periodic purge of expired span rows (per-deployment retention is honoured).
SPAN_PURGE_INTERVAL_S = float(os.environ.get("FLOW_WORKER_SPAN_PURGE_S", "3600"))


# ---------------------------------------------------------------------------
# Sync helpers (call via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _register_worker(worker_id: str, capabilities: dict[str, Any], *, force: bool = False) -> int:
    now = datetime.now(timezone.utc)
    host = socket.gethostname()
    pid = os.getpid()
    with db_session() as s:
        existing = (
            s.execute(select(FeWorker).where(FeWorker.worker_id == worker_id))
            .scalar_one_or_none()
        )
        if existing is None:
            row = FeWorker(
                worker_id=worker_id,
                host=host,
                pid=pid,
                status="active",
                last_heartbeat=now,
                capabilities=capabilities,
            )
            s.add(row)
            s.flush()
            return int(row.id)
        # Prevent accidental duplicate processes using the same worker_id.
        # If an existing active row has a fresh heartbeat, treat it as already running.
        if not force and existing.deleted_at is None and existing.status == "active":
            cutoff = now - timedelta(seconds=DEAD_THRESHOLD_S)
            last = existing.last_heartbeat
            if last is not None and last.tzinfo is None:
                # MySQL may return naive datetimes; treat as UTC.
                last = last.replace(tzinfo=timezone.utc)
            if last is not None and last > cutoff:
                raise RuntimeError(
                    f"worker_id already active: {worker_id} "
                    f"(host={existing.host} pid={existing.pid} last_heartbeat={existing.last_heartbeat.isoformat()})"
                )
        existing.host = host
        existing.pid = pid
        existing.status = "active"
        existing.last_heartbeat = now
        existing.capabilities = capabilities
        existing.deleted_at = None
        return int(existing.id)


def _heartbeat(worker_id: str) -> None:
    with db_session() as s:
        row = (
            s.execute(select(FeWorker).where(FeWorker.worker_id == worker_id))
            .scalar_one_or_none()
        )
        if row is None:
            return
        row.last_heartbeat = datetime.now(timezone.utc)
        if row.status == "dead":
            row.status = "active"


def _mark_worker_dead(worker_id: str) -> None:
    with db_session() as s:
        row = (
            s.execute(select(FeWorker).where(FeWorker.worker_id == worker_id))
            .scalar_one_or_none()
        )
        if row:
            row.status = "dead"


def _list_assignments(worker_id: str) -> list[dict[str, Any]]:
    with db_session() as s:
        stmt = (
            select(FeWorkerAssignment)
            .where(FeWorkerAssignment.worker_id == worker_id)
            .where(FeWorkerAssignment.deleted_at.is_(None))
        )
        return [
            {
                "id": r.id,
                "deployment_id": r.deployment_id,
                "role": r.role,
                "lease_expires_at": r.lease_expires_at,
            }
            for r in s.execute(stmt).scalars().all()
        ]


def _read_deployment(deployment_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeFlowDeployment, deployment_id)
        if row is None or row.deleted_at is not None:
            return None
        return {
            "id": row.id,
            "flow_code": row.flow_code,
            "ver_no": row.ver_no,
            "mode": row.mode,
            "schedule_type": row.schedule_type,
            "schedule_config": row.schedule_config,
            "worker_policy": row.worker_policy,
            "capability_policy": row.capability_policy,
            "status": row.status,
            "env_profile_code": row.env_profile_code,
            "parent_deployment_id": row.parent_deployment_id,
            "observability": row.observability or {},
        }


def _list_all_observability() -> list[tuple[int, dict[str, Any]]]:
    """Return (deployment_id, observability_config) for purging.

    Loaded directly inside the purge loop so policy edits are picked up
    without restarting the worker.
    """
    with db_session() as s:
        stmt = select(FeFlowDeployment.id, FeFlowDeployment.observability).where(
            FeFlowDeployment.deleted_at.is_(None)
        )
        return [(int(dep_id), obs or {}) for dep_id, obs in s.execute(stmt).all()]


def _read_flow_body(flow_code: str, ver_no: int) -> dict[str, Any]:
    with db_session() as s:
        stmt = (
            select(FeFlowVersion)
            .where(FeFlowVersion.flow_code == flow_code)
            .where(FeFlowVersion.ver_no == ver_no)
            .where(FeFlowVersion.deleted_at.is_(None))
        )
        row = s.execute(stmt).scalar_one_or_none()
        if row is None:
            raise FlowEngineError(
                f"flow version not found: flow_code={flow_code} ver_no={ver_no}"
            )
        return json.loads(row.body)


def _once_run_failure_status_detail(
    error: BaseException, *, run_id: int | None
) -> dict[str, Any]:
    from flow_engine.engine.failure_report import (
        FailureCategory,
        failure_report_for_prepare,
        failure_report_from_exception,
        format_failure_text,
    )

    if run_id is None:
        reason = "flow_prepare_failed"
        category = "flow_prepare"
        report = failure_report_for_prepare(error)
    else:
        reason = "run_failed"
        category = "flow_execution"
        report = failure_report_from_exception(
            error,
            category=FailureCategory.FLOW_EXECUTION,
            phase="flow",
        )
    detail = report.to_dict()
    return {
        "reason": reason,
        "category": category,
        "error_type": type(error).__name__,
        "message": format_failure_text(detail),
        "failure_detail": detail,
        "run_id": run_id,
        "ts": detail.get("occurred_at") or datetime.now(timezone.utc).isoformat(),
    }


def _set_deployment_status(
    deployment_id: int,
    status: str,
    *,
    status_detail: dict[str, Any] | None = None,
    clear_status_detail: bool = False,
) -> None:
    with db_session() as s:
        row = s.get(FeFlowDeployment, deployment_id)
        if row is None:
            return
        row.status = status
        if clear_status_detail:
            row.status_detail = None
        elif status_detail is not None:
            row.status_detail = status_detail


def _role_may_execute(
    deployment: dict[str, Any],
    assignment: dict[str, Any],
) -> bool:
    """Whether this assignment's role may execute (subscription / once / cron)."""
    wp = deployment.get("worker_policy") or {}
    wp_type = policy_type_from_policy(wp)
    role = str(assignment.get("role") or "")
    if wp_type == "multi_active":
        return role == "replica"
    return role == "leader"


def _cron_seconds_until_next_fire(deployment_id: int) -> float:
    """Seconds until the next cron slot (minimum 1s when already due)."""
    now = datetime.now(timezone.utc)
    with db_session() as s:
        row = s.get(FeFlowDeployment, int(deployment_id))
        if row is None or row.deleted_at is not None:
            return float(ASSIGNMENT_POLL_INTERVAL_S)
        nxt = scheduler.next_cron_fire_at(row, now=now, session=s)
    if nxt is None:
        return float(ASSIGNMENT_POLL_INTERVAL_S)
    delta = (nxt - now).total_seconds()
    return max(1.0, delta)


def _can_fire_cron(
    deployment: dict[str, Any],
    assignment: dict[str, Any],
) -> bool:
    """Whether this worker may enqueue/execute a cron tick (leader + valid lease)."""
    wp = deployment.get("worker_policy") or {}
    if policy_type_from_policy(wp) == "multi_active":
        return _role_may_execute(deployment, assignment)
    if str(assignment.get("role") or "") != "leader":
        return False
    lease = assignment.get("lease_expires_at")
    if lease is None:
        return True
    if not isinstance(lease, datetime):
        return True
    if lease.tzinfo is None:
        lease = lease.replace(tzinfo=timezone.utc)
    return lease > datetime.now(timezone.utc)


def _can_consume_subscription(
    deployment: dict[str, Any],
    assignment: dict[str, Any],
) -> bool:
    """Whether this worker assignment may run subscription ingress."""
    if not _role_may_execute(deployment, assignment):
        return False
    wp = deployment.get("worker_policy") or {}
    if policy_type_from_policy(wp) == "multi_active":
        return True

    lease = assignment.get("lease_expires_at")
    if lease is None:
        return True
    if not isinstance(lease, datetime):
        return True
    if lease.tzinfo is None:
        lease = lease.replace(tzinfo=timezone.utc)
    return lease > datetime.now(timezone.utc)


def _release_assignment(worker_id: str, deployment_id: int) -> None:
    """Soft-delete the assignment so once deployments don't re-run forever.

    Worker polls ``fe_worker_assignment``; if an assignment row remains after a
    once/cron run finishes, the worker will see it again and start a new run.
    """
    now = datetime.now(timezone.utc)
    with db_session() as s:
        stmt = (
            select(FeWorkerAssignment)
            .where(FeWorkerAssignment.worker_id == worker_id)
            .where(FeWorkerAssignment.deployment_id == deployment_id)
            .where(FeWorkerAssignment.deleted_at.is_(None))
        )
        rows = list(s.execute(stmt).scalars().all())
        for r in rows:
            r.deleted_at = now


# ---------------------------------------------------------------------------
# Worker class
# ---------------------------------------------------------------------------


class Worker:
    """Single Worker process. Use ``await worker.start()`` to begin running."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        max_concurrent_flows: int = 8,
    ) -> None:
        # Default to a stable id so restarts don't create endless worker rows.
        # Override via CLI `--worker-id` or env `FLOW_WORKER_ID` when needed
        # (e.g. multiple workers on one host).
        stable_default = os.environ.get("FLOW_WORKER_ID") or socket.gethostname()
        self.worker_id = (worker_id or stable_default).strip() or socket.gethostname()
        self.capabilities = {"max_concurrent_flows": int(max_concurrent_flows)}
        self._assignments: dict[int, asyncio.Task[Any]] = {}
        self._stop_evt = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._started = False

    # ---------------- lifecycle ----------------

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await asyncio.to_thread(_register_worker, self.worker_id, self.capabilities, force=getattr(self, "_force_register", False))
        logger.info("worker started worker_id=%s", self.worker_id)
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._poll_assignments()))
        # Single worker process is sufficient for span purging — the
        # operation is idempotent (delete-by-date), and only one of the
        # cluster's workers running it is enough. Using a simple
        # always-on loop is operationally cheaper than coordinator
        # election for this background sweeper.
        self._tasks.append(asyncio.create_task(self._purge_loop()))

    async def stop(self) -> None:
        self._stop_evt.set()
        # Cancel running deployments first; pollers next
        for tid, t in list(self._assignments.items()):
            t.cancel()
        for t in list(self._assignments.values()):
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await asyncio.to_thread(_mark_worker_dead, self.worker_id)
        logger.info("worker stopped worker_id=%s", self.worker_id)

    async def run_forever(self) -> None:
        await self.start()
        await self._stop_evt.wait()
        await self.stop()

    # ---------------- background loops ----------------

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._stop_evt.is_set():
                try:
                    await asyncio.to_thread(_heartbeat, self.worker_id)
                except Exception:  # noqa: BLE001
                    logger.exception("heartbeat failed")
                try:
                    await asyncio.wait_for(
                        self._stop_evt.wait(), timeout=HEARTBEAT_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _poll_assignments(self) -> None:
        try:
            while not self._stop_evt.is_set():
                try:
                    rows = await asyncio.to_thread(
                        _list_assignments, self.worker_id
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("assignment poll failed")
                    rows = []

                current = {r["deployment_id"]: r for r in rows}
                # New assignments
                for dep_id, info in current.items():
                    if dep_id not in self._assignments:
                        self._start_assignment(dep_id, info)
                # Removed assignments → cancel
                for dep_id in list(self._assignments.keys()):
                    if dep_id not in current:
                        t = self._assignments.pop(dep_id)
                        t.cancel()

                try:
                    await asyncio.wait_for(
                        self._stop_evt.wait(), timeout=ASSIGNMENT_POLL_INTERVAL_S
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _purge_loop(self) -> None:
        """Periodically drop expired rows from ``fe_run_span``.

        Reads per-deployment ``observability.span_retention_days`` and
        applies the smallest configured value (defensive default = 3
        days) as the global purge horizon. Per-deployment retention is
        honoured because the purge is keyed by ``deploy_run_id``.
        """
        try:
            while not self._stop_evt.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_evt.wait(), timeout=SPAN_PURGE_INTERVAL_S
                    )
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    items = await asyncio.to_thread(_list_all_observability)
                except Exception:  # noqa: BLE001
                    logger.exception("obs config load failed for purge loop")
                    continue
                # Group deployments by retention so we only run a small
                # number of purge passes per cycle.
                from flow_engine.db.models import FeDeployRun  # local to avoid circular cost
                from sqlalchemy import select as _select

                # Build {retention_days: [deployment_ids...]}
                buckets: dict[int, list[int]] = {}
                for dep_id, raw in items:
                    cfg = parse_obs_config(raw or {})
                    buckets.setdefault(cfg.span_retention_days, []).append(dep_id)

                for retention, dep_ids in buckets.items():
                    if not dep_ids:
                        continue
                    # Find the deploy_run rows whose deployment lives in
                    # this retention bucket so we can purge per run.
                    try:
                        def _fetch_run_ids() -> list[int]:
                            with db_session() as s:
                                stmt = _select(FeDeployRun.id).where(
                                    FeDeployRun.deployment_id.in_(dep_ids)
                                )
                                return [int(x) for x in s.execute(stmt).scalars().all()]

                        run_ids = await asyncio.to_thread(_fetch_run_ids)
                    except Exception:  # noqa: BLE001
                        logger.exception("purge loop: list runs failed")
                        continue
                    for rid in run_ids:
                        try:
                            await asyncio.to_thread(
                                span_persistence.purge_old_spans,
                                retention_days=int(retention),
                                deploy_run_id=int(rid),
                            )
                        except Exception:  # noqa: BLE001
                            logger.exception(
                                "purge_old_spans failed run_id=%s retention=%s",
                                rid,
                                retention,
                            )
        except asyncio.CancelledError:
            return

    # ---------------- deployment dispatch ----------------

    def _start_assignment(self, deployment_id: int, info: dict[str, Any]) -> None:
        async def runner() -> None:
            try:
                await self._run_assignment(deployment_id, info)
            except asyncio.CancelledError:
                logger.info("assignment cancelled deployment_id=%s", deployment_id)
                raise
            except Exception:  # noqa: BLE001
                logger.exception(
                    "assignment crashed deployment_id=%s", deployment_id
                )
            finally:
                self._assignments.pop(deployment_id, None)

        self._assignments[deployment_id] = asyncio.create_task(runner())

    async def _await_execute_slot(
        self, deployment_id: int
    ) -> dict[str, Any] | None:
        """Block until this worker may execute once/cron, or return None if assignment ended."""
        while not self._stop_evt.is_set():
            deployment = await asyncio.to_thread(_read_deployment, deployment_id)
            if deployment is None:
                return None
            rows = await asyncio.to_thread(_list_assignments, self.worker_id)
            info = next(
                (r for r in rows if int(r["deployment_id"]) == deployment_id),
                None,
            )
            if info is None:
                return None
            if _role_may_execute(deployment, info):
                return info
            await asyncio.sleep(ASSIGNMENT_POLL_INTERVAL_S)
        return None

    async def _run_assignment(self, deployment_id: int, assignment_info: dict[str, Any]) -> None:
        deployment = await asyncio.to_thread(_read_deployment, deployment_id)
        if deployment is None:
            logger.warning("deployment %s vanished before run", deployment_id)
            return
        st = deployment["schedule_type"]
        try:
            if st == "subscription":
                await self._run_subscription(deployment)
            elif st == "cron":
                await self._run_cron(deployment)
            elif st == "once":
                slot = await self._await_execute_slot(deployment_id)
                if slot is None:
                    return
                await self._run_once_flow(deployment)
            else:
                logger.error("unknown schedule_type=%s for deployment %s", st, deployment_id)
                await asyncio.to_thread(_set_deployment_status, deployment_id, "failed")
        finally:
            # once releases assignment after a single run; cron/subscription keep it.
            if st == "once":
                try:
                    await asyncio.to_thread(_release_assignment, self.worker_id, deployment_id)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "failed to release assignment worker_id=%s deployment_id=%s",
                        self.worker_id,
                        deployment_id,
                    )

    # ---------------- run modes ----------------

    async def _await_cron_fire_slot(
        self, deployment_id: int
    ) -> dict[str, Any] | None:
        """Block until this worker may fire cron, or return None if assignment ended."""
        while not self._stop_evt.is_set():
            deployment = await asyncio.to_thread(_read_deployment, deployment_id)
            if deployment is None:
                return None
            rows = await asyncio.to_thread(_list_assignments, self.worker_id)
            info = next(
                (r for r in rows if int(r["deployment_id"]) == deployment_id),
                None,
            )
            if info is None:
                return None
            if _can_fire_cron(deployment, info):
                return info
            await asyncio.sleep(ASSIGNMENT_POLL_INTERVAL_S)
        return None

    async def _run_cron(self, deployment: dict[str, Any]) -> None:
        """Long-lived loop: sleep until due, enqueue run, execute, repeat."""
        deployment_id = int(deployment["id"])
        try:
            while not self._stop_evt.is_set():
                slot = await self._await_cron_fire_slot(deployment_id)
                if slot is None:
                    return

                deployment = await asyncio.to_thread(_read_deployment, deployment_id)
                if deployment is None:
                    return
                if str(deployment.get("status") or "") != "running":
                    try:
                        await asyncio.wait_for(
                            self._stop_evt.wait(),
                            timeout=ASSIGNMENT_POLL_INTERVAL_S,
                        )
                        return
                    except asyncio.TimeoutError:
                        continue

                enqueued = await asyncio.to_thread(
                    scheduler.enqueue_cron_run_if_due,
                    deployment_id,
                    worker_id=self.worker_id,
                )
                if enqueued is None:
                    wait_s = await asyncio.to_thread(
                        _cron_seconds_until_next_fire, deployment_id
                    )
                    wait_s = min(wait_s, 3600.0)
                    try:
                        await asyncio.wait_for(self._stop_evt.wait(), timeout=wait_s)
                        return
                    except asyncio.TimeoutError:
                        continue

                run_id = await asyncio.to_thread(
                    deploy_persistence.claim_queued_deploy_run,
                    deployment_id,
                    self.worker_id,
                )
                if run_id is None:
                    await asyncio.sleep(ASSIGNMENT_POLL_INTERVAL_S)
                    continue

                await self._execute_cron_run(deployment, run_id)
        except asyncio.CancelledError:
            raise

    async def _execute_cron_run(
        self, deployment: dict[str, Any], run_id: int
    ) -> None:
        deployment_id = int(deployment["id"])
        backend: AsyncBufferedDBBackend | None = None
        try:
            run_id, runtime, profile_id, backend = await self._prepare_runtime(
                deployment,
                trigger_context=None,
                existing_run_id=run_id,
            )
            await backend.start()
            try:
                with profile_scope(profile_id):
                    result = await runtime.run()
            finally:
                try:
                    await backend.drain()
                except Exception:  # noqa: BLE001
                    logger.exception("obs backend drain failed run_id=%s", run_id)
            await asyncio.to_thread(
                deploy_persistence.complete_deploy_run, run_id, result
            )
        except asyncio.CancelledError:
            if backend is not None:
                try:
                    await backend.drain()
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.to_thread(
                deploy_persistence.fail_deploy_run, run_id, "cancelled"
            )
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("cron run failed deployment_id=%s", deployment_id)
            if backend is not None:
                try:
                    await backend.drain()
                except Exception:  # noqa: BLE001
                    pass
            await asyncio.to_thread(
                deploy_persistence.fail_deploy_run, run_id, str(e)
            )

    async def _run_once_flow(self, deployment: dict[str, Any]) -> None:
        deployment_id = int(deployment["id"])
        st = str(deployment.get("schedule_type") or "once")
        run_id: int | None = None
        backend: AsyncBufferedDBBackend | None = None
        try:
            run_id, runtime, profile_id, backend = await self._prepare_runtime(
                deployment, trigger_context=None
            )
            await backend.start()
            try:
                with profile_scope(profile_id):
                    result = await runtime.run()
            finally:
                # Drain (and stop) the obs backend BEFORE marking the
                # run complete so the UI sees consistent counters.
                try:
                    await backend.drain()
                except Exception:  # noqa: BLE001
                    logger.exception("obs backend drain failed run_id=%s", run_id)
            await asyncio.to_thread(
                deploy_persistence.complete_deploy_run, run_id, result
            )
            if st == "once":
                final = "stopped" if result.state == FlowState.COMPLETED else "failed"
                await asyncio.to_thread(_set_deployment_status, deployment_id, final)
        except asyncio.CancelledError:
            if backend is not None:
                try:
                    await backend.drain()
                except Exception:  # noqa: BLE001
                    pass
            if run_id is not None:
                await asyncio.to_thread(deploy_persistence.fail_deploy_run, run_id, "cancelled")
            raise
        except Exception as e:  # noqa: BLE001
            logger.exception("once/cron run failed deployment_id=%s", deployment_id)
            if backend is not None:
                try:
                    await backend.drain()
                except Exception:  # noqa: BLE001
                    pass
            if run_id is not None:
                await asyncio.to_thread(deploy_persistence.fail_deploy_run, run_id, str(e))
            if st == "once":
                await asyncio.to_thread(
                    _set_deployment_status,
                    deployment_id,
                    "failed",
                    status_detail=_once_run_failure_status_detail(e, run_id=run_id),
                )

    async def _await_subscription_consume_slot(
        self, deployment_id: int
    ) -> dict[str, Any] | None:
        """Block until this worker may consume, or return None if assignment ended."""
        warned_lease = False
        while not self._stop_evt.is_set():
            deployment = await asyncio.to_thread(_read_deployment, deployment_id)
            if deployment is None:
                return None
            rows = await asyncio.to_thread(_list_assignments, self.worker_id)
            info = next(
                (r for r in rows if int(r["deployment_id"]) == deployment_id),
                None,
            )
            if info is None:
                return None
            if _can_consume_subscription(deployment, info):
                return info
            if not warned_lease and str(info.get("role") or "") == "leader":
                lease = info.get("lease_expires_at")
                if lease is not None:
                    logger.warning(
                        "subscription leader lease expired or not yet valid "
                        "deployment_id=%s worker_id=%s lease_expires_at=%s",
                        deployment_id,
                        self.worker_id,
                        lease,
                    )
                    warned_lease = True
            await asyncio.sleep(ASSIGNMENT_POLL_INTERVAL_S)
        return None

    async def _run_subscription(self, deployment: dict[str, Any]) -> None:
        from flow_engine.runner.subscription.ingress import (
            SubscriptionIngressError,
            run_subscription_ingress,
        )
        from flow_engine.runner.subscription.spec import (
            ingress_restart_delay_s,
            load_subscription_spec,
        )

        deployment_id = int(deployment["id"])
        spec = load_subscription_spec(deployment.get("schedule_config"))
        wp = deployment.get("worker_policy") or {}
        max_restarts = int(spec.ingress_policy.max_restarts)
        backoff_base = int(spec.ingress_policy.restart_backoff_s)
        restart_count = 0

        async def _clear_ingress_retry_detail() -> None:
            current = await asyncio.to_thread(_read_deployment, deployment_id)
            detail = (current or {}).get("status_detail") or {}
            if detail.get("reason") == "subscription_ingress_retrying":
                await asyncio.to_thread(
                    _set_deployment_status,
                    deployment_id,
                    "running",
                    clear_status_detail=True,
                )

        async def _prepare(deploy: dict[str, Any], trigger_context: dict[str, Any] | None):
            return await self._prepare_runtime(
                deploy,
                trigger_context=trigger_context,
                trigger_type=_subscription_trigger_type(deploy),
            )

        while not self._stop_evt.is_set():
            slot = await self._await_subscription_consume_slot(deployment_id)
            if slot is None:
                return
            try:
                await _clear_ingress_retry_detail()
                await run_subscription_ingress(
                    deployment,
                    stop_evt=self._stop_evt,
                    prepare_runtime=_prepare,
                    worker_id=self.worker_id,
                )
                await _clear_ingress_retry_detail()
                current = await asyncio.to_thread(_read_deployment, deployment_id)
                if current is not None and current.get("status") in ("stopping", "running"):
                    await asyncio.to_thread(_set_deployment_status, deployment_id, "stopped")
                return
            except SubscriptionIngressError as exc:
                detail = {
                    "reason": "subscription_ingress_failed",
                    "code": exc.error.get("code"),
                    "message": exc.error.get("message") or str(exc),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                await asyncio.to_thread(
                    _set_deployment_status,
                    deployment_id,
                    "failed",
                    status_detail=detail,
                )
                await asyncio.to_thread(
                    _release_assignment, self.worker_id, deployment_id
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "subscription ingress failed deployment_id=%s", deployment_id
                )
                restart_count += 1
                err_msg = f"{type(exc).__name__}: {exc}"
                now = datetime.now(timezone.utc)
                if restart_count >= max_restarts:
                    await asyncio.to_thread(
                        _set_deployment_status,
                        deployment_id,
                        "failed",
                        status_detail={
                            "reason": "subscription_ingress_failed",
                            "message": err_msg,
                            "attempts": restart_count,
                            "max_attempts": max_restarts,
                            "ts": now.isoformat(),
                        },
                    )
                    await asyncio.to_thread(
                        _release_assignment, self.worker_id, deployment_id
                    )
                    return
                delay = ingress_restart_delay_s(backoff_base, restart_count)
                next_retry_at = (now + timedelta(seconds=delay)).isoformat()
                await asyncio.to_thread(
                    _set_deployment_status,
                    deployment_id,
                    "running",
                    status_detail={
                        "reason": "subscription_ingress_retrying",
                        "message": err_msg,
                        "attempt": restart_count,
                        "max_attempts": max_restarts,
                        "next_retry_at": next_retry_at,
                        "retry_delay_s": delay,
                        "ts": now.isoformat(),
                    },
                )
                logger.warning(
                    "subscription ingress restart in %.1fs (attempt %d/%d) deployment_id=%s",
                    delay,
                    restart_count,
                    max_restarts,
                    deployment_id,
                )
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=delay)
                    return
                except asyncio.TimeoutError:
                    continue

    # ---------------- runtime construction ----------------

    async def _prepare_runtime(
        self,
        deployment: dict[str, Any],
        *,
        trigger_context: dict[str, Any] | None,
        existing_run_id: int | None = None,
        trigger_type: str | None = None,
    ) -> tuple[int, FlowRuntime, str, AsyncBufferedDBBackend]:
        flow_code = deployment["flow_code"]
        ver_no = int(deployment["ver_no"])
        flow_data = await asyncio.to_thread(_read_flow_body, flow_code, ver_no)
        flow = load_flow_from_dict(copy.deepcopy(flow_data))

        try:
            mode = RunMode(deployment["mode"])
        except ValueError as e:
            raise RunnerConfigError(f"invalid run mode: {deployment['mode']!r}") from e

        rules = [
            CapabilityRule.model_validate(r)
            for r in (deployment.get("capability_policy") or [])
        ]

        profile_id = deployment.get("env_profile_code") or DEFAULT_PROFILE_ID
        dict_tree = await asyncio.to_thread(data_dict.tree_copy, profile_id)
        profile_policy_raw = await asyncio.to_thread(
            lambda: profile_store().get_system_capability_policy(profile_id, run_mode=mode.value)
        )
        profile_rules = [CapabilityRule.model_validate(r) for r in profile_policy_raw]
        run_opts = RunOptions(
            mode=mode,
            mock_overrides={},
            deployment_capability_policy=rules,
            profile_system_capability_policy=profile_rules,
        )

        # Resolve or create the run row first — we need its id for the
        # observability backend's RunRef.
        if existing_run_id is not None:
            run_id = int(existing_run_id)
        else:
            run_id = await asyncio.to_thread(
                deploy_persistence.create_deploy_run,
                deployment_id=int(deployment["id"]),
                worker_id=self.worker_id,
                flow_code=flow_code,
                ver_no=ver_no,
                mode=mode,
                schedule_type=str(deployment.get("schedule_type") or "once"),
                trigger_type=trigger_type or "manual",
                trigger_context=trigger_context,
            )

        obs_cfg = parse_obs_config(deployment.get("observability") or {})
        backend = AsyncBufferedDBBackend(
            run_ref=RunRef(deploy_run_id=run_id),
            flow_code=flow_code,
            obs_cfg=obs_cfg,
        )

        runtime = FlowRuntime(
            flow,
            dictionary=dict_tree,
            run_opts=run_opts,
            obs=backend,
            flow_code=flow_code,
        )
        runtime._obs_run_ref = RunRef(deploy_run_id=run_id)  # type: ignore[attr-defined]
        if trigger_context:
            runtime.ctx.global_ns.update(trigger_context)

        return run_id, runtime, profile_id, backend


def _subscription_trigger_type(_deployment: dict[str, Any]) -> str:
    """Categorical trigger source for ``fe_deploy_run.trigger_type`` (``String(32)``).

    Consumer/topic identity is recorded in ``trigger_context.event_meta``, not here.
    """
    return "subscription"


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------


async def main_async(
    *,
    max_concurrent_flows: int = 8,
    worker_id: str | None = None,
    force: bool = False,
) -> None:
    worker = Worker(worker_id=worker_id, max_concurrent_flows=max_concurrent_flows)
    # internal flag consumed by Worker.start -> _register_worker
    worker._force_register = bool(force)  # type: ignore[attr-defined]
    loop = asyncio.get_running_loop()
    stop_evt = worker._stop_evt  # noqa: SLF001

    def _on_signal() -> None:
        if not stop_evt.is_set():
            logger.info("signal received, stopping worker")
            stop_evt.set()

    # SIGINT / SIGTERM — best-effort; Windows lacks SIGTERM on non-main threads.
    try:
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_: _on_signal())
    except Exception:  # noqa: BLE001
        logger.debug("signal handlers not installed", exc_info=True)

    await worker.run_forever()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="flow-worker", description="Flow Engine Worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start", help="start a worker process")
    p_start.add_argument(
        "--worker-id",
        type=str,
        default=os.environ.get("FLOW_WORKER_ID", ""),
        help="Stable worker id (default: FLOW_WORKER_ID or hostname). "
        "Set explicitly when running multiple workers on one host.",
    )
    p_start.add_argument(
        "--max-concurrent-flows",
        type=int,
        default=int(os.environ.get("FLOW_WORKER_MAX_CONCURRENT", "8")),
    )
    p_start.add_argument(
        "--force",
        action="store_true",
        help="Force start even if the same worker_id appears active (not recommended).",
    )
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.cmd == "start":
        wid = (getattr(args, "worker_id", "") or "").strip() or None
        asyncio.run(
            main_async(
                max_concurrent_flows=args.max_concurrent_flows,
                worker_id=wid,
                force=bool(getattr(args, "force", False)),
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
