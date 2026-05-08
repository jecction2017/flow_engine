"""Persist deployment executions into ``fe_deploy_run`` (Run Center domain).

This module is intentionally isolated from the test domain.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import mean
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from flow_engine.db.models import FeDeployRun
from flow_engine.db.session import db_session

if TYPE_CHECKING:
    from flow_engine.engine.orchestrator import FlowRunResult, NodeRunInfo
    from flow_engine.runner.models import RunMode


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


def complete_deploy_run(
    run_id: int,
    result: "FlowRunResult",
    *,
    is_resident: bool,
) -> None:
    """Mark a deploy run finished and persist payloads."""
    from flow_engine.engine.models import FlowState

    state = result.state
    if state == FlowState.COMPLETED:
        status = "completed"
    elif state == FlowState.TERMINATED:
        status = "terminated"
    else:
        status = "failed"

    flow_logs_json = json.dumps(result.flow_logs, ensure_ascii=False, default=str)
    global_ns: dict[str, Any] | None = None
    try:
        global_ns = dict(getattr(result.context, "global_ns", {}) or {})
        global_ns.pop("dictionary", None)
    except Exception:  # noqa: BLE001
        global_ns = None

    payload: dict[str, Any] = {
        "status": status,
        "finished_at": datetime.now(timezone.utc),
        "flow_logs": flow_logs_json,
    }
    if global_ns is not None:
        payload["global_ns"] = json.dumps(global_ns, ensure_ascii=False, default=str)
    if result.message:
        payload["error"] = result.message

    if is_resident:
        payload["node_stats"] = json.dumps(
            _aggregate_node_stats(result.node_runs),
            ensure_ascii=False,
            default=str,
        )
    else:
        payload["node_runs"] = json.dumps(
            [r.to_dict() for r in result.node_runs],
            ensure_ascii=False,
            default=str,
        )

    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        for k, v in payload.items():
            setattr(row, k, v)


def fail_deploy_run(run_id: int, error: str) -> None:
    """Mark a deploy run failed when no FlowRunResult is available."""
    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        row.status = "failed"
        row.finished_at = datetime.now(timezone.utc)
        row.error = error


def update_iteration_count(run_id: int, count: int) -> None:
    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        row.iteration_count = int(count)


def update_node_stats(run_id: int, stats: dict[str, Any]) -> None:
    with db_session() as s:
        row = s.get(FeDeployRun, int(run_id))
        if row is None:
            return
        row.node_stats = json.dumps(stats, ensure_ascii=False, default=str)


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
        stmt = stmt.order_by(FeDeployRun.started_at.desc())

        all_rows = list(s.execute(stmt).scalars().all())
        total = len(all_rows)
        page = all_rows[offset : offset + limit]

        def _run_dict(r: FeDeployRun) -> dict[str, Any]:
            return {
                "id": int(r.id),
                "deployment_id": int(r.deployment_id),
                "test_batch_id": None,
                "flow_code": r.flow_code,
                "ver_no": int(r.ver_no),
                "mode": r.mode,
                "schedule_type": r.schedule_type,
                "trigger_type": r.trigger_type,
                "status": r.status,
                "worker_id": r.worker_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "iteration_count": r.iteration_count,
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
            "test_batch_id": None,
            "worker_id": row.worker_id,
            "flow_code": row.flow_code,
            "ver_no": int(row.ver_no),
            "mode": row.mode,
            "schedule_type": row.schedule_type,
            "trigger_type": row.trigger_type,
            "trigger_context": row.trigger_context,
            "status": row.status,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "iteration_count": row.iteration_count,
            "node_runs": _safe_json_load(row.node_runs),
            "node_stats": _safe_json_load(row.node_stats),
            "flow_logs": _safe_json_load(row.flow_logs),
            "global_ns": _safe_json_load(row.global_ns),
            "error": row.error,
            "evaluation": None,
        }


# ---------------------------------------------------------------------------
# Aggregation helpers (resident)
# ---------------------------------------------------------------------------


def _aggregate_node_stats(runs: "list[NodeRunInfo]") -> dict[str, Any]:
    from flow_engine.engine.models import NodeState

    per_node: dict[str, dict[str, Any]] = {}
    for r in runs:
        rec = per_node.setdefault(
            r.node_id,
            {"count": 0, "success": 0, "failed": 0, "_durations": []},
        )
        rec["count"] += 1
        if r.final_state == NodeState.SUCCESS:
            rec["success"] += 1
        elif r.final_state == NodeState.FAILED:
            rec["failed"] += 1
        if r.duration_ms is not None:
            rec["_durations"].append(r.duration_ms)
    out_per_node: dict[str, Any] = {}
    for node_id, rec in per_node.items():
        durs: list[int] = rec.pop("_durations")
        rec["avg_ms"] = int(round(mean(durs))) if durs else 0
        rec["p99_ms"] = _percentile(durs, 0.99) if durs else 0
        out_per_node[node_id] = rec
    return {
        "per_node": out_per_node,
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    idx = int(round(q * (len(s) - 1)))
    return int(s[max(0, min(idx, len(s) - 1))])


def _safe_json_load(value: str | None) -> Any:
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value

