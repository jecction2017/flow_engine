"""Persist deployment executions into ``fe_deploy_run`` (Run Center domain).

Observability blobs have been removed; details live in ``fe_run_span`` and
``fe_node_metric``. This module is now just lifecycle plumbing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from flow_engine.db.models import FeDeployRun, FeFlowDeployment
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat

if TYPE_CHECKING:
    from flow_engine.engine.orchestrator import FlowRunResult
    from flow_engine.runner.models import RunMode


def flow_run_failure_message(result: "FlowRunResult") -> str:
    """Human-readable failure summary for deploy/test run rows and ledgers."""
    from flow_engine.engine.failure_report import failure_text_from_run_result
    from flow_engine.engine.models import NodeState

    failed = sorted(
        nid for nid, st in (result.node_state or {}).items() if st == NodeState.FAILED
    )
    return failure_text_from_run_result(
        message=result.message,
        failure_report=result.failure_report,
        failed_node_ids=failed or None,
        state_value=result.state.value,
    )

_FLOW_LOGS_MAX = 500


def _extract_global_ns(result: "FlowRunResult") -> dict[str, Any] | None:
    """Snapshot ``global_ns`` for run-detail APIs (strip internal dictionary)."""
    gns = dict(getattr(result.context, "global_ns", {}) or {})
    gns.pop("dictionary", None)
    return gns or None


def _normalize_flow_logs(logs: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not logs:
        return None
    if len(logs) <= _FLOW_LOGS_MAX:
        return logs
    trimmed = [dict(e) for e in logs[:_FLOW_LOGS_MAX]]
    trimmed.append(
        {
            "level": "warn",
            "message": f"flow_logs truncated to {_FLOW_LOGS_MAX} entries",
            "ts_ms": 0,
            "source": "system",
            "truncated": True,
        }
    )
    return trimmed


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _allocate_deploy_run_no(session, deployment_id: int) -> int:
    """Next per-deployment run sequence (1-based). Caller must be in a transaction."""
    mx = session.execute(
        select(func.coalesce(func.max(FeDeployRun.run_no), 0)).where(
            FeDeployRun.deployment_id == int(deployment_id)
        )
    ).scalar_one()
    return int(mx) + 1


def deploy_run_no_map(session, run_ids: set[int]) -> dict[int, int]:
    """Map global deploy run id → per-deployment ``run_no``."""
    if not run_ids:
        return {}
    rows = session.execute(
        select(FeDeployRun.id, FeDeployRun.run_no).where(
            FeDeployRun.id.in_(run_ids),
            FeDeployRun.deleted_at.is_(None),
        )
    ).all()
    return {int(rid): int(rno) for rid, rno in rows}


def backfill_deploy_run_numbers() -> int:
    """Assign ``run_no`` by ``id`` order within each deployment. Returns rows updated."""
    updated = 0
    with db_session() as s:
        dep_ids = list(
            s.execute(
                select(FeDeployRun.deployment_id)
                .where(FeDeployRun.deleted_at.is_(None))
                .distinct()
            ).scalars().all()
        )
        for dep_id in dep_ids:
            rows = list(
                s.execute(
                    select(FeDeployRun)
                    .where(FeDeployRun.deployment_id == int(dep_id))
                    .where(FeDeployRun.deleted_at.is_(None))
                    .order_by(FeDeployRun.id.asc())
                ).scalars().all()
            )
            for i, row in enumerate(rows, start=1):
                if int(row.run_no) != i:
                    row.run_no = i
                    updated += 1
    return updated


def create_deploy_run(
    *,
    deployment_id: int,
    worker_id: str | None,
    flow_code: str,
    ver_no: int,
    mode: "RunMode",
    schedule_type: str,
    trigger_type: str,
    trigger_context: dict[str, Any] | None,
) -> int:
    """Insert ``FeDeployRun(status='running')`` and return the new run id."""
    now = datetime.now(timezone.utc)
    with db_session() as s:
        dep = s.get(FeFlowDeployment, int(deployment_id), with_for_update=True)
        if dep is None or dep.deleted_at is not None:
            raise ValueError(f"deployment {deployment_id} not found")
        run_no = _allocate_deploy_run_no(s, deployment_id)
        row = FeDeployRun(
            deployment_id=int(deployment_id),
            run_no=run_no,
            worker_id=worker_id,
            flow_code=flow_code,
            ver_no=int(ver_no),
            mode=mode.value,
            schedule_type=str(schedule_type or "once"),
            trigger_type=str(trigger_type or "manual"),
            trigger_context=trigger_context,
            status="running",
            started_at=now,
        )
        s.add(row)
        s.flush()
        return int(row.id)


def claim_queued_deploy_run(deployment_id: int, worker_id: str) -> int | None:
    """FIFO-claim the oldest queued run for ``deployment_id``; returns run id or None."""
    with db_session() as s:
        row = (
            s.execute(
                select(FeDeployRun)
                .where(FeDeployRun.deployment_id == int(deployment_id))
                .where(FeDeployRun.status == "queued")
                .where(FeDeployRun.deleted_at.is_(None))
                .order_by(FeDeployRun.id.asc())
                .limit(1)
                .with_for_update()
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        now = datetime.now(timezone.utc)
        row.status = "running"
        row.worker_id = worker_id
        row.started_at = now
        s.flush()
        return int(row.id)


def complete_deploy_run(run_id: int, result: "FlowRunResult") -> None:
    """Mark a deploy run finished. No blob columns — span/metric tables
    hold the detail."""
    from flow_engine.engine.models import FlowState

    state = result.state
    if state == FlowState.COMPLETED:
        status = "completed"
    elif state == FlowState.TERMINATED:
        status = "terminated"
    else:
        status = "failed"

    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        row.status = status
        row.finished_at = datetime.now(timezone.utc)
        if status == "failed":
            row.error = flow_run_failure_message(result)
            row.failure_detail = (
                dict(result.failure_report) if result.failure_report else None
            )
        elif result.message:
            row.error = result.message
        row.flow_logs = _normalize_flow_logs(list(result.flow_logs))
        row.global_ns = _extract_global_ns(result)


def fail_deploy_run(run_id: int, error: str) -> None:
    """Mark a deploy run failed when no FlowRunResult is available."""
    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        row.status = "failed"
        row.finished_at = datetime.now(timezone.utc)
        row.error = error


# ---------------------------------------------------------------------------
# Listing helpers (used by HTTP API)
# ---------------------------------------------------------------------------


def list_deploy_runs(
    *,
    deployment_id: int | None = None,
    flow_code: str | None = None,
    mode: str | None = None,
    status: str | None = None,
    worker_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with db_session() as s:
        stmt = select(FeDeployRun).where(FeDeployRun.deleted_at.is_(None))
        if deployment_id is not None:
            stmt = stmt.where(FeDeployRun.deployment_id == int(deployment_id))
        if flow_code:
            stmt = stmt.where(FeDeployRun.flow_code == flow_code)
        if mode:
            stmt = stmt.where(FeDeployRun.mode == mode)
        if status:
            stmt = stmt.where(FeDeployRun.status == status)
        if worker_id:
            stmt = stmt.where(FeDeployRun.worker_id == worker_id)
        stmt = stmt.order_by(
            func.coalesce(FeDeployRun.started_at, FeDeployRun.created_at).desc()
        )

        all_rows = list(s.execute(stmt).scalars().all())
        total = len(all_rows)
        page = all_rows[offset : offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "runs": [_serialize_deploy_run_summary(r) for r in page],
        }


def _serialize_deploy_run_summary(row: FeDeployRun) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "run_no": int(row.run_no),
        "deployment_id": int(row.deployment_id),
        "flow_code": row.flow_code,
        "ver_no": int(row.ver_no),
        "mode": row.mode,
        "schedule_type": row.schedule_type,
        "trigger_type": row.trigger_type,
        "status": row.status,
        "worker_id": row.worker_id,
        "started_at": utc_isoformat(row.started_at),
        "finished_at": utc_isoformat(row.finished_at),
        "span_count": int(row.span_count) if row.span_count is not None else None,
        "sampled_span_count": (
            int(row.sampled_span_count) if row.sampled_span_count is not None else None
        ),
        "error": row.error,
        "failure_detail": (
            dict(row.failure_detail) if row.failure_detail else None
        ),
    }


# Run Center overview: non-failed latest run per deployment (failed has its own panel).
_OVERVIEW_RUN_STATUSES = ("queued", "running", "completed", "terminated")


def list_recent_deploy_runs_per_deployment(
    *,
    status: str | None = None,
    statuses: tuple[str, ...] | None = None,
    since: datetime | None = None,
    hours: float = 24,
    offset: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """Latest deploy run per deployment for given status(es) within a lookback window."""
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=float(hours))
    elif since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    if statuses is not None:
        status_filter = tuple(statuses)
    elif status is not None:
        status_filter = (str(status),)
    else:
        raise ValueError("status or statuses is required")

    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 200))
    activity_at = func.coalesce(
        FeDeployRun.finished_at,
        FeDeployRun.started_at,
        FeDeployRun.created_at,
    )

    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    with db_session() as s:
        rows = list(
            s.execute(
                select(FeDeployRun)
                .where(FeDeployRun.deleted_at.is_(None))
                .where(FeDeployRun.status.in_(status_filter))
                .where(activity_at >= since)
                .order_by(activity_at.desc(), FeDeployRun.id.desc())
            ).scalars().all()
        )
        for row in rows:
            dep_id = int(row.deployment_id)
            if dep_id in seen:
                continue
            seen.add(dep_id)
            deduped.append(_serialize_deploy_run_summary(row))

    return {
        "since": utc_isoformat(since),
        "offset": offset,
        "limit": limit,
        "total": len(deduped),
        "runs": deduped[offset : offset + limit],
    }


def list_recent_failed_deploy_runs(
    *,
    since: datetime | None = None,
    hours: float = 24,
    offset: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """Latest failed deploy run per deployment within a lookback window."""
    return list_recent_deploy_runs_per_deployment(
        status="failed",
        since=since,
        hours=hours,
        offset=offset,
        limit=limit,
    )


def list_recent_overview_deploy_runs(
    *,
    since: datetime | None = None,
    hours: float = 24,
    offset: int = 0,
    limit: int = 10,
) -> dict[str, Any]:
    """Latest non-failed deploy run per deployment within a lookback window."""
    return list_recent_deploy_runs_per_deployment(
        statuses=_OVERVIEW_RUN_STATUSES,
        since=since,
        hours=hours,
        offset=offset,
        limit=limit,
    )


def get_deploy_run_detail(run_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None or row.deleted_at is not None:
            return None
        return {
            "id": int(row.id),
            "run_no": int(row.run_no),
            "deployment_id": int(row.deployment_id),
            "worker_id": row.worker_id,
            "flow_code": row.flow_code,
            "ver_no": int(row.ver_no),
            "mode": row.mode,
            "schedule_type": row.schedule_type,
            "trigger_type": row.trigger_type,
            "trigger_context": row.trigger_context,
            "status": row.status,
            "started_at": utc_isoformat(row.started_at),
            "finished_at": utc_isoformat(row.finished_at),
            "span_count": int(row.span_count) if row.span_count is not None else None,
            "sampled_span_count": (
                int(row.sampled_span_count) if row.sampled_span_count is not None else None
            ),
            "error": row.error,
            "failure_detail": (
                dict(row.failure_detail) if row.failure_detail else None
            ),
            "flow_logs": list(row.flow_logs) if row.flow_logs else None,
            "global_ns": dict(row.global_ns) if row.global_ns else None,
        }
