"""Persist deployment executions into ``fe_deploy_run`` (Run Center domain).

Observability blobs have been removed; details live in ``fe_run_span`` and
``fe_node_metric``. This module is now just lifecycle plumbing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from flow_engine.db.models import FeDeployRun
from flow_engine.db.session import db_session
from flow_engine.time_utils import utc_isoformat

if TYPE_CHECKING:
    from flow_engine.engine.orchestrator import FlowRunResult
    from flow_engine.runner.models import RunMode

_FLOW_LOGS_MAX = 500


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
        row = FeDeployRun(
            deployment_id=int(deployment_id),
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
        if result.message:
            row.error = result.message
        row.flow_logs = _normalize_flow_logs(list(result.flow_logs))


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

        def _run_dict(r: FeDeployRun) -> dict[str, Any]:
            return {
                "id": int(r.id),
                "deployment_id": int(r.deployment_id),
                "flow_code": r.flow_code,
                "ver_no": int(r.ver_no),
                "mode": r.mode,
                "schedule_type": r.schedule_type,
                "trigger_type": r.trigger_type,
                "status": r.status,
                "worker_id": r.worker_id,
                "started_at": utc_isoformat(r.started_at),
                "finished_at": utc_isoformat(r.finished_at),
                "span_count": int(r.span_count) if r.span_count is not None else None,
                "sampled_span_count": (
                    int(r.sampled_span_count) if r.sampled_span_count is not None else None
                ),
                "error": r.error,
            }

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "runs": [_run_dict(r) for r in page],
        }


def get_deploy_run_detail(run_id: int) -> dict[str, Any] | None:
    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None or row.deleted_at is not None:
            return None
        return {
            "id": int(row.id),
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
            "flow_logs": list(row.flow_logs) if row.flow_logs else None,
        }
